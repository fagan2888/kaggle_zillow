# Main script
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import LabelEncoder
import lightgbm as lgb
import gc
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from sklearn.metrics import mean_absolute_error as mae
from sklearn.metrics import mean_squared_error as mse
from sklearn.model_selection import KFold, train_test_split
import random
import datetime as dt
from datetime import datetime
from data_setup import data_set
from algorithms import algorithms
import time
import sys
import pickle

class house_model(object):

    def __init__(self,prop_file,train_file,df_pkl,sample_file,columns_df,log_entry,data_option):

        # Note: The redudancy in variables names for using self is because
        # of laziness to make self. changes all the way down. In the interest of
        # time, I will make the change later.

        # Insatantiate files
        self.prop_file = prop_file
        prop_file = self.prop_file
        self.train_file = train_file
        train_file = self.train_file
        self.df_pkl = df_pkl
        df_pkl = self.df_pkl
        self.sample_file = sample_file
        sample_file = self.sample_file
        self.columns_df = columns_df
        columns_df = self.columns_df
        self.columns = columns_df["columns"].values.tolist()
        self.log_entry = log_entry
        self.data_option = data_option


    def house_train(self,weights,light_gbm_params,xgb_params_1,num_boost_rounds_1,
                    xgb_params_2,num_boost_rounds_2,type = "test"):
        # Start time
        t1 = time.time()

        # Weights of different models
        self.XGB_WEIGHT = weights[0]
        self.BASELINE_WEIGHT = weights[1]
        self.OLS_WEIGHT = weights[2]
        self.XGB1_WEIGHT = weights[3]  # Weight of first in combination of two XGB models
        self.BASELINE_PRED = weights[4]   # Baseline based on mean of training data, per Oleg

        # Instantiate data
        data = data_set(prop_file,train_file,df_pkl,sample_file,self.columns)
        #------ Light gbm data---------------------
        prop = data.get_prop(self.data_option['lgbm'])
        train_org = data.get_train()
        #----------------------------------------------------

        # KFold Cross Validation
        [m,n]  = train_org.shape
        k = 4
        kf = KFold(n_splits=k)
        result_metrics = np.zeros((k,3))
        count = 0
        models = []

        rand_state_1 = 2
        test_size_1 = 0.1

        X_train1,X_test1 = train_test_split(train_org.index,random_state=rand_state_1,test_size=test_size_1)
        train_set = train_org.iloc[X_train1]
        test_set_org = train_org[["parcelid","transactiondate"]].iloc[X_test1]

        for train_index, test_index in kf.split(train_set):

            print("#########################################################")
            print("#########################################################")
            print("#########################################################")
            print("#########################################################")
            print("########                              ###################")
            print("########     Starting Model: %g        ###################" %(count+1))
            print("########                              ###################")
            print("#########################################################")
            print("#########################################################")
            print("#########################################################")

            if type == "submission":
                test_set_ret = data.get_sample_submission()
                train = data.get_train()

            elif type == "test":
                train = train_set.iloc[train_index]
                sample = train_set[["parcelid","transactiondate"]].iloc[test_index]
                y_cv = train_set["logerror"].iloc[test_index].values
                test_set = sample

            # LGB //////////////////////////////////////////////
            self.algo_lgb = algorithms(prop,train)
            lgb_model = self.algo_lgb.train_light_gbm(light_gbm_params)
            if type == 'test':
                lgb_pred = self.algo_lgb.predict_light_gbm(lgb_model,sample)

            # ----- XGB Data-------------------------------------------------
            properties = data.get_prop(self.data_option['xgb']).copy()
            if type == "test":
                train = train_set.iloc[train_index]
                sample = train_set[["parcelid","transactiondate"]].iloc[test_index]
                y_cv = train_set["logerror"].iloc[test_index].values
                test_set = sample
            #----------------------------------------------------------------

            # XGB //////////////////////////////////////////////////////////
            self.algo_xgb = algorithms(properties,train)

            xgb_model1 = self.algo_xgb.train_xgboost(xgb_params_1,num_boost_rounds_1)
            xgb_model2 = self.algo_xgb.train_xgboost(xgb_params_2,num_boost_rounds_2)

            if type == "test":
                test_parcelid_df = sample[["parcelid"]]
                xgb_pred1 = self.algo_xgb.predict_xgb(xgb_model1,test_parcelid_df)
                xgb_pred2 = self.algo_xgb.predict_xgb(xgb_model2,test_parcelid_df)

                del properties; gc.collect()
            # --------OLS data---------------------------------------------------
            properties = data.get_prop(self.data_option['ols']).copy()

            if type == "test":
                train = train_set.iloc[train_index]
                sample = train_set[["parcelid","transactiondate"]].iloc[test_index]
                y_cv = train_set["logerror"].iloc[test_index].values
                test_set = sample
            #-------------------------------------------------------------------

            # OLS ////////////////////////////////////////////////////////////
            self.algo_ols = algorithms(properties,train,train_path =train_file )
            ols_model = self.algo_ols.train_OLS(properties)

            # collect the models
            models.append([lgb_model,xgb_model1,xgb_model2,ols_model])

            # set default scores
            score = np.array([0.,0.,0.])

            if type =="test":
                ##### COMBINE RESULTS
                xgb_pred = self.XGB1_WEIGHT*xgb_pred1 + (1-self.XGB1_WEIGHT)*xgb_pred2
                print( "\nCombining XGBoost, LightGBM, and baseline predicitons ..." )
                lgb_weight = (1 - self.XGB_WEIGHT - self.BASELINE_WEIGHT) / (1 - self.OLS_WEIGHT)
                xgb_weight0 = self.XGB_WEIGHT / (1 - self.OLS_WEIGHT)
                baseline_weight0 =  self.BASELINE_WEIGHT / (1 - self.OLS_WEIGHT)
                pred0 = xgb_weight0*xgb_pred + baseline_weight0*self.BASELINE_PRED + lgb_weight*lgb_pred

                # Predict with OLS
                print( "\nPredicting with OLS and combining with XGB/LGB/baseline predicitons: ..." )
                test_date = sample["transactiondate"].values
                ols_pred = self.algo_ols.predict_OLS(ols_model,test_date,sample,properties)
                pred = self.OLS_WEIGHT*ols_pred + (1-self.OLS_WEIGHT)*pred0

                # Calculate metrics
                model_mae = mae(y_cv,pred)
                model_mse = mse(y_cv,pred)
                model_r2 = r2_score(y_cv,pred)

                result_metrics[count,:] = np.array([model_mae,model_mse,model_r2])
                count += 1

            # Average the score across all models
            score = np.mean(result_metrics,axis=0)
            print("MAE: %g, MSE: %g, R2: %g" %(score[0],score[1],score[2]))

        # End time
        exec_time = time.time() - t1
        print("Execution Time: %g seconds" %exec_time)

        # Log entires
        self.log_entry['Models'] = models
        self.log_entry['CV_MAE'] = score[0]
        self.log_entry['CV_MSE'] = score[1]
        self.log_entry['CV_R2'] = score[2]
        self.log_entry['Training_time'] = exec_time

        if type == "test":
            test_set_ret = train_org[["parcelid","transactiondate","logerror"]].iloc[X_test1]

        del properties; gc.collect()
        del prop; gc.collect()

        return score, models, test_set_ret, self.log_entry

    def house_pred(self,models,sample,type = "test"):

        t2 = time.time()
        # define data
        data2 = data_set(prop_file,train_file,df_pkl,sample_file,self.columns)
        # required for ols only
        properties = data2.get_prop(self.data_option['ols']).copy()

        [m,n] = sample.shape

        if type == "test":
            y = sample["logerror"].values
            sample = sample.drop(["logerror"],axis=1)
            test_parcelid_df = sample[["parcelid"]]

        elif type == "submission":
            y = np.zeros(m)
            sample["parcelid"] = sample["ParcelId"]
            test_parcelid_df = sample[["parcelid"]]

        # Test dates
        test_dates = ['2016-10-01','2016-11-01','2016-12-01','2017-10-01','2017-11-01','2017-12-01']
        test_columns = ['201610','201611','201612','201710','201711','201712']

        num_models = len(models)

        # Initilize outputs
        model_mae = 0.
        model_mse = 0.
        model_r2 = 0.
        logerr_mat = np.zeros((m,len(test_columns))) # for 6 test dates

        for i in range(num_models):
            lgb_model = models[i][0]
            xgb_model1 = models[i][1]
            xgb_model2 = models[i][2]
            ols_model = models[i][3]

            lgb_pred = self.algo_lgb.predict_light_gbm(lgb_model,sample)

            xgb_pred1 = self.algo_xgb.predict_xgb(xgb_model1,test_parcelid_df)
            xgb_pred2 = self.algo_xgb.predict_xgb(xgb_model2,test_parcelid_df)

            ##### COMBINE RESULTS
            xgb_pred = self.XGB1_WEIGHT*xgb_pred1 + (1-self.XGB1_WEIGHT)*xgb_pred2
            print( "\nCombining XGBoost, LightGBM, and baseline predicitons ..." )
            lgb_weight = (1 - self.XGB_WEIGHT - self.BASELINE_WEIGHT) / (1 - self.OLS_WEIGHT)
            xgb_weight0 = self.XGB_WEIGHT / (1 - self.OLS_WEIGHT)
            baseline_weight0 =  self.BASELINE_WEIGHT / (1 - self.OLS_WEIGHT)
            pred0 = xgb_weight0*xgb_pred + baseline_weight0*self.BASELINE_PRED + lgb_weight*lgb_pred

            if type == "test":
                print( "\nPredicting with OLS and combining with XGB/LGB/baseline predicitons: ..." )
                test_date = sample["transactiondate"].values
                ols_pred = self.algo_ols.predict_OLS(ols_model,test_date,sample,properties)
                pred = self.OLS_WEIGHT*ols_pred + (1-self.OLS_WEIGHT)*pred0

                # Calculate metrics
                model_mae += mae(y,pred)
                model_mse += mse(y,pred)
                model_r2 += r2_score(y,pred)

            elif type == "submission":
                print( "\nPredicting with OLS and combining with XGB/LGB/baseline predicitons: ..." )
                for i in range(len(test_dates)):
                    ols_model = self.algo_ols.train_OLS(properties)
                    ols_pred = self.algo_ols.predict_OLS(ols_model,test_dates[i],sample,properties)
                    pred = self.OLS_WEIGHT*ols_pred + (1-self.OLS_WEIGHT)*pred0
                    submission = sample
                    submission[test_columns[i]] = [float(format(x, '.4f')) for x in pred]
                    print('predict...', i)

                print( "\nCombined XGB/LGB/baseline/OLS predictions:" )
                submission  = submission.drop(["parcelid"],axis=1)
                sub_mat = submission.as_matrix()
                logerr_mat += sub_mat[:,1::]

        if type == "submission":
            logerr_mat = logerr_mat/float(num_models)
            sub_mat[:,1::] = logerr_mat
            sub_dict = {}
            sub_dict["ParcelId"] = sub_mat[:,0].astype(int)
            for i in range(len(test_columns)):
                sub_dict[test_columns[i]] = sub_mat[:,i+1]
            submission = pd.DataFrame(sub_dict)
            cols = ["ParcelId"] + test_columns
            submission = submission[cols]
            return submission

        elif type == "test":
            print("MAE: %g, MSE: %g, R2: %g" %(model_mae/num_models,
                                model_mse/num_models,model_r2/num_models))
            return [model_mae/num_models,model_mse/num_models,model_r2/num_models]



    def write_results(self,submission,id):
        # Write the results to the file
        print( "\nWriting results to disk ..." )
        submission.to_csv('sub_' + str(id) + '.csv', index=False)
        print( "\nFinished ...")

if __name__ == '__main__':

    # Set data files
    #prop_file = "../data/properties_2016.csv"
    #train_file = "../data/train_2016_v2.csv"
    #df_pkl = "../data/full_df_v2.pkl"
    #sample_file = "../data/sample_submission.csv"

    # Set data files - Testing
    prop_file = "./data_for_testing/prop_sample.csv"
    train_file = "./data_for_testing/train_sample.csv"
    df_pkl = "./data_for_testing/df_full_sample.pkl"
    sample_file = "./data_for_testing/sample_submission_for_testing.csv"

    columns_df = pd.read_csv("columns.csv")

    # data_Options
    option_1 = "original"
    option_2 =  "filled_w_median"
    option_3 = "filled_w_-1"
    option_4 = "filled_knn_-1"
    option_5 = "filled_knn_median"
    #--------------------------------------------------------------------------
    # ------------------------------INPUTS-------------------------------------
    # -------------------------------------------------------------------------
    data_option = {}
    data_option['lgbm'] = option_1
    data_option['xgb'] = option_1
    data_option['ols'] = option_1

    # Run type
    # test or submission
    #type = "submission"
    type = "test"

    # Weights of different models
    XGB_WEIGHT = 0.6415
    BASELINE_WEIGHT = 0.0056
    OLS_WEIGHT = 0.0828
    XGB1_WEIGHT = 0.8083  # Weight of first in combination of two XGB models
    BASELINE_PRED = 0.0115   # Baseline based on mean of training data, per Oleg

    weights = [XGB_WEIGHT,BASELINE_WEIGHT,OLS_WEIGHT,XGB1_WEIGHT,BASELINE_PRED]

    # LigthGBM Parameters
    light_gbm_params = {}
    light_gbm_params['max_bin'] = 10
    light_gbm_params['learning_rate'] = 0.0021 # shrinkage_rate
    light_gbm_params['boosting_type'] = 'gbdt'
    light_gbm_params['objective'] = 'regression'
    light_gbm_params['metric'] = 'l1'          # or 'mae'
    light_gbm_params['sub_feature'] = 0.345
    light_gbm_params['bagging_fraction'] = 0.85 # sub_row
    light_gbm_params['bagging_freq'] = 40
    light_gbm_params['num_leaves'] = 512        # num_leaf
    light_gbm_params['min_data'] = 10         # min_data_in_leaf
    light_gbm_params['min_hessian'] = 0.05     # min_sum_hessian_in_leaf
    light_gbm_params['verbose'] = 0
    light_gbm_params['feature_fraction_seed'] = 2
    light_gbm_params['bagging_seed'] = 3

    # XGBoost Parameters
    xgb_params_1 = {
        'eta': 0.037,
        'max_depth': 5,
        'subsample': 0.80,
        'objective': 'reg:linear',
        'eval_metric': 'mae',
        'lambda': 0.8,
        'alpha': 0.4,
        'base_score': 0.,
        'silent': 1
    }
    num_boost_rounds_1 = 250

    xgb_params_2 = {
        'eta': 0.033,
        'max_depth': 6,
        'subsample': 0.80,
        'objective': 'reg:linear',
        'eval_metric': 'mae',
        'lambda': 1.0,
        'alpha': 0,
        'base_score': 0.,
        'silent': 1
    }
    num_boost_rounds_2 = 150

    #--------------------------------------------------------------------------
    # ------------------------END of INPUTS------------------------------------
    # -------------------------------------------------------------------------

    # Initialize dataframes

    log_df = pd.read_pickle("./logs/log_df.pkl")

    # Set unique ID for each run
    id = int(datetime.now().strftime('%Y%m%d%H%M%S'))

    log_entry = {}
    log_entry['ID'] = id
    log_entry["data_lgbm"] = data_option['lgbm']
    log_entry["data_xgb"] = data_option['xgb']
    log_entry["data_ols"] = data_option['ols']
    log_entry['Status'] = 0. # Status

    # Note about the data and the run_xgboost
    note = "submission, testing output"
    log_entry['Note'] = note

    # Traing the models
    log_entry['Run_type'] = type
    house = house_model(prop_file,train_file,df_pkl,sample_file,columns_df,
                        log_entry,data_option)

    score, models, test_set, log_entry = house.house_train(weights,
                                        light_gbm_params,
                                        xgb_params_1,num_boost_rounds_1,
                                        xgb_params_2,num_boost_rounds_2,
                                        type=type)

    print("Validation Score:")
    print("MAE            MSE           R2")
    print score

    # Final Prediction
    out = house.house_pred(models,test_set,type = type)

    if type == "test":
        print("Score:")
        print out
        log_entry['Test_MAE'] = out[0]
        log_entry['Test_MSE'] = out[1]
        log_entry['Test_R2'] = out[2]

    if type == "submission":
        house.write_results(out,id)
        log_entry['Test_MAE'] = 0.
        log_entry['Test_MSE'] = 0.
        log_entry['Test_R2'] = 0.

    log_entry['Status'] = 1. # Status = 1, if run is successful

    # Update logging dataframes

    print("Writing log dataframes")
    # Run Log
    log_df =  log_df.append(pd.DataFrame([log_entry],columns = log_entry.keys()))
    log_df.to_pickle("./logs/log_df.pkl")

    # Parameters log
    lgbm_params_df = pd.read_pickle("./logs/lgbm_params_df.pkl")
    lgbm_params_df = lgbm_params_df.append(pd.DataFrame([light_gbm_params]),ignore_index=True)
    lgbm_params_df["ID"].iloc[-1] = id
    lgbm_params_df.to_pickle("./logs/lgbm_params_df.pkl")

    xgb_params_1_df = pd.read_pickle("./logs/xgb_params_1_df.pkl")
    xgb_params_1_df = xgb_params_1_df.append(pd.DataFrame([xgb_params_1]),ignore_index=True)
    xgb_params_1_df["ID"].iloc[-1] = id
    xgb_params_1_df.to_pickle("./logs/xgb_params_1_df.pkl")

    xgb_params_2_df = pd.read_pickle("./logs/xgb_params_2_df.pkl")
    xgb_params_2_df = xgb_params_2_df.append(pd.DataFrame([xgb_params_2]),ignore_index=True)
    xgb_params_2_df["ID"].iloc[-1] = id
    xgb_params_2_df.to_pickle("./logs/xgb_params_2_df.pkl")

    #backup_pkl_path = ""
    log_df.to_pickle("./back_up_logs/backup_log" + str(id) + ".pkl")

    print("FINISHED-----------------------------------------")
