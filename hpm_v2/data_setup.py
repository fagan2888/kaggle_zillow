# Data Module

import numpy as np
import pandas as pd
import random
import datetime as dt
import gc
import sys

class data_set(object):

    def __init__(self,prop_file,train_file,df_pkl,sample_file,columns):

        print("Reading properties file.......\n")
        self.prop_raw = pd.read_csv(prop_file)
        self.columns = columns
        self.prop_raw = self.prop_raw[self.columns]
        print("Reading train file.......\n")
        self.train_raw = pd.read_csv(train_file)
        print("Reading full df pkl.......\n")
        self.df_full = pd.read_pickle(df_pkl)
        print("Reading sample file.......\n")
        self.sample = pd.read_csv(sample_file)

    def get_train(self):
        return self.train_raw

    def get_sample_submission(self):
        return self.sample

    def get_prop(self,option,threshold=0.9):

        if option == "original":
            print("Selected original prop")
            return self.prop_raw

        elif option == "filled_w_median":
            print("Selected median filled prop")
            prop = self.prop_raw.fillna(self.prop_raw.median(),inplace = True)
            return prop

        elif option == "filled_w_-1":
            print("Selected -1 filled prop")
            for c in self.prop_raw.columns:
                self.prop_raw[c]=self.prop_raw[c].fillna(-1)
            return self.prop_raw

        elif option == "filled_w_knn_-1":
            self.n_rows,self.n_columns = self.df_full.shape

            # Prop df with filled data without the last 11437 empty rows
            self.prop_filled_A = self.df_full.loc[90275::].drop(["logerror","transactiondate"],axis=1).reset_index()
            self.prop_filled_A = self.prop_filled_A.drop(["index"],axis=1)

            # prop df including 11437 empty rows
            self.prop_filled_B = pd.concat([self.prop_filled_A,self.prop_raw.loc[2973780::]],ignore_index=True)

            # Filter to active features which meet threshold for filled %
            na_perct = self.df_full.isnull().sum().values/(self.n_rows*1.0)
            df_na_summary = pd.DataFrame(self.df_full.columns.tolist(),columns=["Feature"])
            df_na_summary["% NA"] = na_perct
            active_features = df_na_summary["Feature"][df_na_summary["% NA"] <= threshold].values

            for c in self.prop_filled_B.columns:
                self.prop_filled_B[c]=self.prop_filled_B[c].fillna(-1)
            print("Selected knn and -1 filled prop")
            return prop_filled_B[active_features]

        elif option == "filled_w_knn_median":
            self.n_rows,self.n_columns = self.df_full.shape

            # Prop df with filled data without the last 11437 empty rows
            self.prop_filled_A = self.df_full.loc[90275::].drop(["logerror","transactiondate"],axis=1).reset_index()
            self.prop_filled_A = self.prop_filled_A.drop(["index"],axis=1)

            # prop df including 11437 empty rows
            self.prop_filled_B = pd.concat([self.prop_filled_A,self.prop_raw.loc[2973780::]],ignore_index=True)

            # Filter to active features which meet threshold for filled %
            na_perct = self.df_full.isnull().sum().values/(self.n_rows*1.0)
            df_na_summary = pd.DataFrame(self.df_full.columns.tolist(),columns=["Feature"])
            df_na_summary["% NA"] = na_perct
            active_features = df_na_summary["Feature"][df_na_summary["% NA"] <= threshold].values

            prop = self.prop_filled_B.fillna(self.prop_filled_B.median(),inplace = True)
            print("Selected knn and median filled prop")
            return prop[active_features]
