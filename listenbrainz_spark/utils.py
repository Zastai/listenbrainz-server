import os
import sys
import errno
import logging
import traceback
from py4j.protocol import Py4JJavaError

import listenbrainz_spark
from listenbrainz_spark import stats
from listenbrainz_spark import config
from listenbrainz_spark.stats import run_query

from pyspark.sql.utils import AnalysisException

def create_path(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def register_dataframe(df, table_name):
    """ Creates a view to be used for Spark SQL, etc. Replaces the view if a view with the
        same name exists.

        Args:
            df (dataframe): Dataframe to register.
            table_name (str): Name of the view.
    """
    try:
        df.createOrReplaceTempView(table_name)
    except Py4JJavaError as err:
        raise Py4JJavaError('Cannot register dataframe "{}": {}\n'.format(table_name, type(err).__name__),
            err.java_exception)

def read_files_from_HDFS(path):
    """ Loads the dataframe stored at the given path in HDFS.

        Args:
            path (str): An HDFS path.
    """
    try:
        df = listenbrainz_spark.sql_context.read.parquet(path)
        return df
    except AnalysisException as err:
      raise AnalysisException('Cannot read "{}" from HDFS: {}\n'.format(path, type(err).__name__),
            stackTrace=traceback.format_exc())
    except Py4JJavaError as err:
        raise Py4JJavaError('An error occurred while fetching "{}": {}\n'.format(path, type(err).__name__),
            err.java_exception)

def get_listens(df, date):
    """ Fetch listens of the date and append with the dataframe, both passed as arguments.

        Args:
            df (dataframe): None or with columns as:
                [
                    'artist_mbids', 'artist_msid', 'artist_name', 'listened_at', 'recording_mbid'
                    'recording_msid', 'release_mbid', 'release_msid', 'release_name', 'tags',
                    'track_name', 'user_name'
                ]
            date (datetime): Date for which listens are to be fetched.

        Returns:
            df (dataframe): Columns can be depicted as:
                [
                    'artist_mbids', 'artist_msid', 'artist_name', 'listened_at', 'recording_mbid'
                    'recording_msid', 'release_mbid', 'release_msid', 'release_name', 'tags',
                    'track_name', 'user_name'
                ]
    """
    month = read_files_from_HDFS('{}/data/listenbrainz/{}/{}.parquet'.format(config.HDFS_CLUSTER_URI, date.year, date.month))
    df = df.union(month) if df else month
    return df

def get_listens_for_train_model_window(begin_date, end_date):
    """ Load listens listened to in a given time window from HDFS.

        Args:
            begin_date (datetime): Date to start fetching listens.
            end_date (datetime): Date upto which listens should be fetched. Usually the current date.

        Returns:
            df (dataframe): Columns can be depicted as:
                [
                    'artist_mbids', 'artist_msid', 'artist_name', 'listened_at', 'recording_mbid'
                    'recording_msid', 'release_mbid', 'release_msid', 'release_name', 'tags',
                    'track_name', 'user_name'
                ]
        Note: Listens of current month will not be fetched.
    """
    df = None
    while begin_date < end_date:
        df = get_listens(df, begin_date)
        # incrementing months
        begin_date = stats.adjust_months(begin_date, 1)
    return df

def get_listens_for_rec_generation_winodw(begin_date, end_date):
    """ Load listens listenend to in a given time window from HDFS.

        Args:
            begin_date (datetime): Date to start fetching listens.
            end_date (datetime): Date upto which listens should be fetched. Usually the current date.

        Returns:
            df (dataframe): Columns can be depicted as:
                [
                    'artist_mbids', 'artist_msid', 'artist_name', 'listened_at', 'recording_mbid'
                    'recording_msid', 'release_mbid', 'release_msid', 'release_name', 'tags',
                    'track_name', 'user_name'
                ]
        Note: Listens of current month will be fetched.
    """
    df = None
    while begin_date <= end_date:
        df = get_listens(df, begin_date)
        # incrementing days
        begin_date = stats.adjust_days(begin_date, config.RECOMMENDATION_GENERATION_WINDOW)
    return df

def save_parquet(df, path):
    """ Save dataframe as parquet to given path in HDFS.

        Args:
            df (dataframe): Dataframe to save.
            path (str): Path in HDFS to save the dataframe.
    """
    try:
        df.write.format('parquet').save(path, mode='overwrite')
    except Py4JJavaError as err:
        raise Py4JJavaError('Cannot save parquet to {}: {}\n'.format(path, type(err).__name__), err.java_exception)
