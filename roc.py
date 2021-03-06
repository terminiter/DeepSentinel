import argparse
import pickle
from pathlib import Path
import glob
import os
import sys
from storages import log_store
from storages.log_store import LogStore
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='ROC')
    parser.add_argument('logfile', metavar='Target', help='Log to be analyzed')
    parser.add_argument('scorefile', metavar='Scores', help='Scores')
    parser.add_argument('imagefile', nargs='?', metavar='Image', default=None, help='Save image file')
    args = parser.parse_args()

    #print("loading log file...")
    logname = Path(args.logfile).stem
    logpath = (Path('output') / logname).with_suffix('.pickle')

    if logpath.exists():
        with logpath.open(mode='rb') as logstorefile:
            log_store = pickle.load(logstorefile)
    else:
        sys.exit('No log file.')

    #print("loading score file...")
    scores = pd.read_csv(args.scorefile, header=None, names=['score'])

    log = pd.concat([log_store.log, scores], axis=1, join='inner')

    n_a = log[('P6','Normal/Attack')]
    normal_dummy = pd.get_dummies(n_a)['Normal']
    log['Normal'] = normal_dummy
    log['Attack'] = 1 - normal_dummy

    log = log.sort_values(by='score', ascending=False)

    correct_detection = log['Attack'].cumsum()
    false_detection = log['Normal'].cumsum()

    recall = correct_detection / (log['Attack'].sum())
    fp = false_detection / (log['Normal'].sum())
    log['False Positive'] = fp
    log['True Positive'] = recall

    log.plot.scatter(x='False Positive', y='True Positive', color='lightblue', lw = 0)
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.axis([0, 1, 0, 1])
    if args.imagefile is None:
        plt.show()
    else:
        plt.savefig(args.imagefile)
