import pickle
import itertools
import functools
import chainer
import math
import numpy as np
from chainer import cuda, optimizers
from rnns import logLSTM
from rnns.logLSTM import LogLSTM
from tqdm import tqdm

def contiguousarray(xp, a, dtype):
    return xp.ascontiguousarray(xp.array(a, dtype=dtype), dtype=dtype)

def convert_to_array(xp, a):
    return [contiguousarray(xp, a[0], dtype=xp.int32),
        contiguousarray(xp, a[1], dtype=xp.int32),
        contiguousarray(xp, a[2], dtype=xp.int32),
        contiguousarray(xp, a[3], dtype=xp.float32)]

def _training_seq(xp, log_store, i):
    for j in range(log_store.chunk_size):
        labels = []
        notes = []
        commands = []
        vals = []
        for k in [k for k in range(log_store.chunk_num) if not k == i]:
            labels.append(log_store.label_seqs[k][j])
            notes.append(log_store.note_seqs[k][j])
            commands.append(log_store.command_seqs[k][j])
            vals.append(log_store.value_seqs[k][j])
            data = [labels, notes, commands, vals]
        yield convert_to_array(xp, data)

def _eval_seq(xp, log_store, i):
    for j in tqdm(range(log_store.chunk_size)):
        yield  convert_to_array(xp, [[log_store.label_seqs[i][j]],
        [log_store.note_seqs[i][j]],
        [log_store.command_seqs[i][j]],
        [log_store.value_seqs[i][j]]])


class LogModel:
    def __init__(self, log_store, chunk, n_units=1000, tr_sq_ln=100, gpu=-1, directory=''):
        self.log_store = log_store
        self.chunk = chunk
        self.n_units= n_units
        self.tr_sq_ln = tr_sq_ln
        self.gpu = gpu
        self.dir = directory
        self.current_epoch = 0
        self.model = LogLSTM(log_store.label_num, log_store.note_num, log_store.command_num, self.n_units)

    def train(self, epoch):
        xp = np
        if self.gpu >= 0:
            print("Use GPU ", self.gpu)
            xp = cuda.cupy

        if self.current_epoch >= epoch:
            pass
        else:
            model = self.model
            if self.gpu >= 0:
                cuda.get_device(self.gpu).use()
                model.to_gpu()

            optimizer = optimizers.Adam()
            optimizer.setup(model)

            for j in tqdm(range(self.current_epoch+1, epoch+1)):
                model.reset_state()
                train_seq = _training_seq(xp, self.log_store, self.chunk)
                cur, nt = itertools.tee(train_seq)
                nt = itertools.islice(nt, 1, None)
                data = zip(cur, nt)
                for k in tqdm(range(0, self.log_store.chunk_size, self.tr_sq_ln)):
                    model.cleargrads()
                    data_seq = list(itertools.islice(data, self.tr_sq_ln))
                    loss = model(data_seq)
                    loss.backward()
                    loss.unchain_backward()
                    optimizer.update()

                self.current_epoch = j
                self.save()
                model.reset_state()
                loss = self.eval()
                with open(self.dir+"stat-{}-{}.csv".format(self.chunk, self.n_units),'a') as statfile:
                    print(j, ',',  2**loss, file=statfile)

    def _eval(self):
        xp = np
        if self.gpu >= 0:
            xp = cuda.cupy
        self.model.reset_state()
        eval_seq = _eval_seq(xp, self.log_store, self.chunk)
        cur, nt = itertools.tee(eval_seq)
        nt = itertools.islice(nt, 1, None)
        data = zip(cur, nt)
        return (self.model.eval(cur, nt, volatile='on').data for cur, nt in data)

    def eval(self):
        count = 0
        sum_loss = 0
        with open(self.dir+"outlier-factors-{}-{}-{}.csv".format(self.chunk, self.n_units, self.current_epoch), 'w') as f:
            for outlier_factor in self._eval():
                sum_loss += outlier_factor
                print(self.log_store.ID_seqs[self.chunk][count], ',', outlier_factor, file=f)
                count += 1
        return sum_loss / (self.log_store.chunk_size - 1)

    def save(self):
        with open(self.dir+"log_model-{}-{}-{}.pickle".format(self.chunk, self.n_units, self.current_epoch), 'wb') as f:
            pickle.dump(self, f)