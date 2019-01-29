# -*- coding: utf-8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
Created on Mon Jan 11 13:34:37 2019

@author: giang nguyen
@author: stefan dlugolinsky
"""

import io
import json
import os
import tempfile
from zipfile import ZipFile

import keras
import pandas as pd
from keras.callbacks import EarlyStopping
from keras.callbacks import ModelCheckpoint
from keras.layers import Bidirectional
from keras.layers import Dense
from keras.layers import Flatten
from keras.layers import Input
from keras.layers import RepeatVector
from keras.layers.convolutional import Conv1D
from keras.layers.convolutional import MaxPooling1D
from keras.layers.recurrent import GRU
from keras.layers.recurrent import LSTM
from keras.models import Model
from keras.preprocessing.sequence import TimeseriesGenerator
from sklearn.externals import joblib
from sklearn.preprocessing import MinMaxScaler

# import project config.py
import mods.config as cfg


class mods_model:
    # generic
    __FILE = 'file'
    # model
    __MODEL = 'model'
    __MULTIVARIATE = 'multivariate'
    __SEQUENCE_LEN = 'sequence_len'
    __MODEL_DELTA = 'model_delta'
    __INTERPOLATE = 'interpolate'
    __MODEL_TYPE = 'model_type'
    __EPOCHS = 'epochs'
    __EPOCHS_PATIENCE = 'epochs_patience'
    __BLOCKS = 'blocks'
    # scaler
    __SCALER = 'scaler'
    # sample data
    __SAMPLE_DATA = 'sample_data'
    __SEP = 'sep'
    __SKIPROWS = 'skiprows'
    __SKIPFOOTER = 'skipfooter'
    __ENGINE = 'engine'
    __USECOLS = 'usecols'

    def __init__(self, file):
        self.file = file
        self.name = os.path.basename(file)
        self.config = None
        self.model = None
        self.__scaler = None
        self.sample_data = None
        if os.path.isfile(file):
            self.__load(file)
            self.__init()
        else:
            self.config = self.__default_config()

    # saves the contents of the original file (e.g. file in a zip) into a temp file and runs func over it
    def __func_over_tempfile(self, orig_file, func, mode='wb', *args, **kwargs):
        # create temp file
        _, fname = tempfile.mkstemp()
        with open(fname, mode) as tf:
            # extract model to the temp file
            tf.write(orig_file.read())
            # call the func over the temp file
            result = func(fname, *args, **kwargs)
        # remove the temp file
        os.remove(fname)
        return result

    def __get_sample_data_cfg(self):
        if mods_model.__SAMPLE_DATA in self.config:
            return self.config[mods_model.__SAMPLE_DATA]
        return None

    def save(self):
        print('Saving model: %s' % self.file)
        with ZipFile(self.file, mode='w') as zip:
            self.__save_config(zip, 'config.json')
            self.__save_model(zip, self.config[mods_model.__MODEL])
            self.__save_scaler(zip, self.config[mods_model.__SCALER])
            self.__save_sample_data(zip, self.__get_sample_data_cfg())
        print('Model saved')

    def __load(self, file):
        print('Loading model: %s' % file)
        with ZipFile(file) as zip:
            self.__load_config(zip, 'config.json')
            self.__load_model(zip, self.config[mods_model.__MODEL])
            self.__load_scaler(zip, self.config[mods_model.__SCALER])
            self.__load_sample_data(zip, self.__get_sample_data_cfg())
        print('Model loaded')

    def __save_config(self, zip, file):
        with zip.open(file, mode='w') as f:
            data = json.dumps(self.config)
            f.write(bytes(data, 'utf-8'))

    def __load_config(self, zip, file):
        print('Loading model config')
        with zip.open(file) as f:
            data = f.read()
            self.config = json.loads(data.decode('utf-8'))
        print('Model config:\n%s' % json.dumps(self.config, indent=True))

    def __save_model(self, zip, model_config):
        print('Saving keras model')
        _, fname = tempfile.mkstemp()
        self.model.save(fname)
        zip.write(fname, model_config[mods_model.__FILE])
        os.remove(fname)
        print('Keras model saved')

    def __load_model(self, zip, model_config):
        print('Loading keras model')
        with zip.open(model_config[mods_model.__FILE]) as f:
            self.model = self.__func_over_tempfile(f, keras.models.load_model)
        print('Keras model loaded')

    def __save_scaler(self, zip, scaler_config):
        print('Saving scaler')
        _, fname = tempfile.mkstemp()
        joblib.dump(self.__scaler, fname)
        zip.write(fname, scaler_config[mods_model.__FILE])
        os.remove(fname)
        print('Scaler saved')

    def __load_scaler(self, zip, scaler_config):
        print('Loading scaler')
        with zip.open(scaler_config[mods_model.__FILE]) as f:
            self.__scaler = joblib.load(f)
        print('Scaler loaded')

    def __save_sample_data(self, zip, sample_data_config):
        if sample_data_config is None:
            return
        if self.sample_data is None:
            print('No sample data was set')
            return
        print('Saving sample data')
        with zip.open(sample_data_config[mods_model.__FILE], mode='w') as f:
            self.sample_data.to_csv(
                io.TextIOWrapper(f),
                sep=sample_data_config[mods_model.__SEP],
                skiprows=sample_data_config[mods_model.__SKIPROWS],
                skipfooter=sample_data_config[mods_model.__SKIPFOOTER],
                engine=sample_data_config[mods_model.__ENGINE],
                usecols=lambda col: col in sample_data_config[mods_model.__USECOLS]
            )
        print('Sample data saved:\n%s' % self.sample_data)

    def __load_sample_data(self, zip, sample_data_config):
        if sample_data_config is None:
            return
        print('Loading sample data')
        with zip.open(sample_data_config[mods_model.__FILE]) as f:
            self.sample_data = pd.read_csv(
                io.TextIOWrapper(f),
                sep=sample_data_config[mods_model.__SEP],
                skiprows=sample_data_config[mods_model.__SKIPROWS],
                skipfooter=sample_data_config[mods_model.__SKIPFOOTER],
                engine=sample_data_config[mods_model.__ENGINE],
                usecols=lambda col: col in sample_data_config[mods_model.__USECOLS]
            )
        print('Sample data loaded:\n%s' % self.sample_data)

    def load_data(self, path, sep='\t', skiprows=0, skipfooter=0, engine='python',
                  usecols=lambda col: col in ['number_of_conn', 'sum_orig_kbytes']):
        df = pd.read_csv(
            open(path),
            sep=sep,
            skiprows=skiprows,
            skipfooter=skipfooter,
            engine=engine,
            usecols=usecols
        )
        return df

    def __default_config(self):
        return {
            mods_model.__MODEL: {
                mods_model.__FILE: 'model.h5',
                mods_model.__MULTIVARIATE: len(cfg.usecols),
                mods_model.__SEQUENCE_LEN: cfg.sequence_len,
                mods_model.__MODEL_DELTA: cfg.model_delta,
                mods_model.__INTERPOLATE: cfg.interpolate,
                mods_model.__MODEL_TYPE: cfg.model_type,
                mods_model.__EPOCHS: cfg.n_epochs,
                mods_model.__EPOCHS_PATIENCE: cfg.epochs_patience,
                mods_model.__BLOCKS: cfg.blocks
            },
            mods_model.__SCALER: {
                mods_model.__FILE: 'scaler.pkl'
            }
        }

    def cfg_model(self):
        return self.config[mods_model.__MODEL]

    def set_multivariate(self, multivariate):
        self.cfg_model()[mods_model.__MULTIVARIATE] = multivariate

    def get_multivariate(self):
        return self.cfg_model()[mods_model.__MULTIVARIATE]

    def set_sequence_len(self, sequence_len):
        self.cfg_model()[mods_model.__SEQUENCE_LEN] = sequence_len

    def get_sequence_len(self):
        return self.cfg_model()[mods_model.__SEQUENCE_LEN]

    def set_model_delta(self, model_delta):
        self.cfg_model()[mods_model.__MODEL_DELTA] = model_delta

    def isdelta(self):
        return self.cfg_model()[mods_model.__MODEL_DELTA]

    def set_interpolate(self, interpolate):
        self.cfg_model()[mods_model.__INTERPOLATE] = interpolate

    def get_interpolate(self):
        return self.cfg_model()[mods_model.__INTERPOLATE]

    def set_model_type(self, model_type):
        self.cfg_model()[mods_model.__MODEL_TYPE] = model_type

    def get_model_type(self):
        return self.cfg_model()[mods_model.__MODEL_TYPE]

    def set_epochs(self, epochs):
        self.cfg_model()[mods_model.__EPOCHS] = epochs

    def get_epochs(self):
        return self.cfg_model()[mods_model.__EPOCHS]

    def set_epochs_patience(self, epochs_patience):
        self.cfg_model()[mods_model.__EPOCHS_PATIENCE] = epochs_patience

    def get_epochs_patience(self):
        return self.cfg_model()[mods_model.__EPOCHS_PATIENCE]

    def set_blocks(self, blocks):
        self.cfg_model()[mods_model.__BLOCKS] = blocks

    def get_blocks(self):
        return self.cfg_model()[mods_model.__BLOCKS]

    def get_scaler(self):
        if not self.__scaler:
            self.__scaler = MinMaxScaler(feature_range=(0, 1))
        return self.__scaler

    def set_scaler(self, scaler):
        self.__scaler = scaler

    def set_sample_data(self, df):
        self.sample_data = df

    def train(
            self,
            df_train,
            multivariate=cfg.multivariate,
            sequence_len=cfg.sequence_len,
            model_delta=cfg.model_delta,
            interpolate=cfg.interpolate,
            model_type=cfg.model_type,
            n_epochs=cfg.n_epochs,
            epochs_patience=cfg.epochs_patience,
            blocks=cfg.blocks
    ):
        if multivariate is None:
            multivariate = self.get_multivariate()
        else:
            self.set_multivariate(multivariate)
        if sequence_len is None:
            sequence_len = self.get_sequence_len()
        else:
            self.set_sequence_len(sequence_len)
        if model_delta is None:
            model_delta = self.isdelta()
        else:
            self.set_model_delta(model_delta)
        if interpolate is None:
            interpolate = self.get_interpolate()
        else:
            self.set_interpolate(interpolate)
        if model_type is None:
            model_type = self.get_model_type()
        else:
            self.set_model_type(model_type)
        if n_epochs is None:
            n_epochs = self.get_epochs()
        else:
            self.set_epochs(n_epochs)
        if epochs_patience is None:
            epochs_patience = self.get_epochs_patience()
        else:
            self.set_epochs_patience(epochs_patience)
        if blocks is None:
            blocks = self.get_blocks()
        else:
            self.set_blocks(blocks)

        # Define model
        # TODO: divide into multiple model classes according to model_type
        x = Input(shape=(sequence_len, multivariate))
        if model_type == 'GRU':
            h = GRU(blocks)(x)
        elif model_type == 'bidirect':
            h = Bidirectional(LSTM(blocks))(x)
        elif model_type == 'seq2seq':
            h = LSTM(blocks)(x)
            h = RepeatVector(sequence_len)(h)
            h = LSTM(blocks, return_sequences=True)(h)
            h = Flatten()(h)
        elif model_type == 'CNN':
            h = Conv1D(filters=64, kernel_size=2, activation='relu')(x)
            h = MaxPooling1D(pool_size=2)(h)
            h = Flatten()(h)
        elif model_type == 'MLP':
            h = Dense(units=multivariate, activation='relu')(x)
            # h = Dense(units=multivariate, activation='relu')(h)
            h = Flatten()(h)
        else:  # default LSTM
            h = LSTM(blocks)(x)
            # h = LSTM(blocks)(h)         # stacked

        y = Dense(units=multivariate, activation='sigmoid')(h)  # 'softmax'

        self.model = Model(inputs=x, outputs=y)

        # Drawing model
        print(self.model.summary())

        # Compile model
        self.model.compile(loss='mean_squared_error',
                           optimizer='adam',  # 'adagrad', 'rmsprop'
                           metrics=['mse', 'mae', 'mape'])  # 'cosine'

        # Checkpointing and earlystopping
        filepath = cfg.app_checkpoints + self.name + '-{epoch:02d}.hdf5'
        checkpoints = ModelCheckpoint(
            filepath,
            monitor='loss',
            save_best_only=True,
            mode=max,
            verbose=1
        )
        earlystops = EarlyStopping(
            monitor='loss',
            patience=epochs_patience,
            verbose=1
        )
        callbacks_list = [checkpoints, earlystops]

        if self.get_interpolate():
            df_train.interpolate(inplace=True)

        df_train = df_train.values.astype('float32')
        df_train = self.transform(df_train)
        df_train = self.normalize(df_train, self.get_scaler())

        tsg_train = self.get_tsg(df_train)

        # TODO: remove later
        print(self.config)

        self.model.fit_generator(
            tsg_train,
            epochs=n_epochs,
            callbacks=callbacks_list
        )

    def plot(self, *args):
        print('this method is not yet implemented')

    def __init(self):
        print('Initializing model')
        if self.sample_data is not None:
            self.predict(self.sample_data)
        print('Model initialized')

    # First order differential for numpy array      y' = d(y)/d(t) = f(y,t)
    # be carefull                                   len(dt) == len(data)-1
    # e.g., [5,2,9,1] --> [2-5,9-2,1-9] == [-3,7,-8]
    def delta(self, df):
        return df[1:] - df[:-1]

    def transform(self, df):
        if self.isdelta():
            return self.delta(df)
        else:
            # bucketing, taxo, fuzzy
            return df

    def inverse_transform(self, original, transformed, prediction):
        if self.isdelta():
            beg = self.get_sequence_len()
            end = beg + len(prediction)
            y = original[beg + 1:end + 1]
            return y - transformed[beg:end] + prediction
        else:
            return prediction

    # normalizes data
    def normalize(self, df, scaler):
        # Scale all metrics but each separately
        df = scaler.fit_transform(df)
        return df

    # inverse method to @normalize
    def inverse_normalize(self, df):
        return self.get_scaler().inverse_transform(df)

    # returns time series generator
    def get_tsg(self, df):
        return TimeseriesGenerator(df,
                                   df,
                                   length=self.get_sequence_len(),
                                   sampling_rate=1,
                                   stride=1,
                                   batch_size=1)

    def predict(self, df):

        if self.get_interpolate():
            interpol = df.interpolate()
            interpol = interpol.values.astype('float32')
            # print('interpolated:\n%s' % interpol)

        trans = self.transform(interpol)
        # print('transformed:\n%s' % transf)

        norm = self.normalize(trans, self.get_scaler())
        # print('normalized:\n%s' % norm)

        tsg = self.get_tsg(norm)
        pred = self.model.predict_generator(tsg)
        # print('prediction:\n%s' % pred)

        denorm = self.inverse_normalize(pred)
        # print('denormalized:\n%s' % denorm)

        invtrans = self.inverse_transform(interpol, trans, denorm)
        # print('inverse transformed:\n%s' % invtrans)

        return invtrans
