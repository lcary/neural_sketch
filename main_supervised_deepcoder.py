#Sketch project
from builtins import super
import pickle
import string
import argparse
import random
import torch
from torch import nn, optim
from pinn import RobustFill
from pinn import SyntaxCheckingRobustFill #TODO
import random
import math
import time
from collections import OrderedDict
#from util import enumerate_reg, Hole

import sys
sys.path.append("/om/user/mnye/ec")
from grammar import Grammar, NoCandidates
from program import Application, Hole, Primitive, Index, Abstraction, ParseFailure
from type import Context, arrow, tint, tlist, tbool, UnificationFailure
from deepcoderPrimitives import deepcoderProductions, flatten_program
from utilities import timing

from makeDeepcoderData import batchloader
import math
from deepcoder_util import parseprogram, grammar, tokenize_for_robustfill
from itertools import chain

parser = argparse.ArgumentParser()
parser.add_argument('--pretrain', action='store_true')
parser.add_argument('--debug', action='store_true')
parser.add_argument('--nosave', action='store_true')
#parser.add_argument('--start_with_holes', action='store_true')
#parser.add_argument('--variance_reduction', action='store_true')
parser.add_argument('-k', type=int, default=3) #TODO
parser.add_argument('--new', action='store_true')
parser.add_argument('--rnn_max_length', type=int, default=30)
parser.add_argument('--batchsize', type=int, default=200)
parser.add_argument('--Vrange', type=int, default=128)
parser.add_argument('--n_examples', type=int, default=5)
parser.add_argument('--max_list_length', type=int, default=10)
parser.add_argument('--max_n_inputs', type=int, default=3)
parser.add_argument('--max_pretrain_epochs', type=int, default=4)
parser.add_argument('--max_epochs', type=int, default=10)
parser.add_argument('--train_data', nargs='*', 
    default=['data/DeepCoder_data/T2_A2_V512_L10_train.txt', 'data/DeepCoder_data/T3_A2_V512_L10_train_perm.txt'])
# save and load files
parser.add_argument('--load_pretrained_model_path', type=str, default="./deepcoder_pretrained.p")
parser.add_argument('--save_pretrained_model_path', type=str, default="./deepcoder_pretrained.p")
parser.add_argument('--save_model_path', type=str, default="./deepcoder_holes.p")
parser.add_argument('--save_freq', type=int, default=200)
parser.add_argument('--print_freq', type=int, default=1)
parser.add_argument('--top_k_sketches', type=int, default=100)
parser.add_argument('--inv_temp', type=float, default=1.0)
args = parser.parse_args()

batchsize = args.batchsize 
Vrange = args.Vrange
train_datas = args.train_data

def deepcoder_vocab(grammar, n_inputs=args.max_n_inputs): 
    return [prim.name for prim in grammar.primitives] + ['input_' + str(i) for i in range(n_inputs)] + ['<HOLE>']  # TODO
vocab = deepcoder_vocab(grammar)

if __name__ == "__main__":
    print("Loading model", flush=True)
    try:
        if args.new: raise FileNotFoundError
        else:
            model=torch.load(args.load_pretrained_model_path)
            print('found saved model, loaded pretrained model (without holes)')
    except FileNotFoundError:
        print("no saved model, creating new one")
        model = SyntaxCheckingRobustFill(
            input_vocabularies=[list(range(-Vrange, Vrange+1)) + ["LIST_START", "LIST_END"],
            list(range(-Vrange, Vrange+1)) + ["LIST_START", "LIST_END"]], 
            target_vocabulary=vocab, max_length=args.rnn_max_length, hidden_size=512)  # TODO
        model.pretrain_iteration = 0
        model.pretrain_scores = []
        model.pretrain_epochs = 0
        model.iteration = 0
        model.hole_scores = []
        model.epochs = 0

    model.cuda()
    print("number of parameters is", sum(p.numel() for p in model.parameters() if p.requires_grad))


    ####### train with holes ########
    pretraining = args.pretrain and model.pretrain_epochs < args.max_pretrain_epochs
    training = model.epochs < args.max_epochs

    t2 = time.time()
    while pretraining or training:
        j = model.pretrain_epochs if pretraining else model.epochs
        if pretraining: print(f"\tpretraining epoch {j}:")
        else: print(f"\ttraining epoch {j}:")
        path = args.save_pretrained_model_path if pretraining else args.save_model_path
        for i, batch in enumerate(batchloader(train_datas,
                                                batchsize=batchsize,
                                                N=args.n_examples,
                                                V=Vrange,
                                                L=args.max_list_length, 
                                                compute_sketches=not pretraining,
                                                top_k_sketches=args.top_k_sketches,
                                                inv_temp=args.inv_temp)):
            IOs = tokenize_for_robustfill(batch.IOs)
            t = time.time()
            objective, syntax_score = model.optimiser_step(IOs, batch.pseqs if pretraining else batch.sketchseqs)
            print(f"network time: {time.time()-t}, other time: {t-t2}")
            t2 = time.time()
            if pretraining:
                model.pretrain_scores.append(objective)
                model.pretrain_iteration += 1
            else:
                model.iteration += 1
                model.hole_scores.append(objective)
            if i%args.print_freq==0: 
                print("iteration", i, "score:", objective, "syntax_score:", syntax_score, flush=True)
            if i%args.save_freq==0: 
                if not args.nosave:
                    torch.save(model, path+f'_{str(j)}_iter_{str(i)}.p')
                    torch.save(model, path)
        if not args.nosave:
            torch.save(model, path+'_{}.p'.format(str(j)))
            torch.save(model, path)
        if pretraining: model.pretrain_epochs += 1
        else: model.epochs += 1
        if model.pretrain_epochs >= args.max_pretrain_epochs: pretraining = False
        if model.epochs >= args.max_epochs: training = False

        ####### End train with holes ########

# RL formalism w luke
# add temperature parameter - x 
# think about RL objective

# merge pretrain and regular train - x 
# use with timing(nn training) - idk 
# deal with model attributes - x
