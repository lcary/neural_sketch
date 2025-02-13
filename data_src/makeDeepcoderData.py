#generate deepcoder data
import sys
import os
sys.path.append(os.path.abspath('./'))
sys.path.append(os.path.abspath('./ec'))

import pickle
from util.deepcoder_util import parseprogram, make_holey_deepcoder
from util.deepcoder_util import grammar as basegrammar
import time
from collections import namedtuple
#Function = namedtuple('Function', ['src', 'sig', 'fun', 'bounds'])

from grammar import Grammar, NoCandidates
from utilities import flatten

from deepcoderPrimitives import deepcoderProductions, flatten_program
from program import Application, Hole, Primitive, Index, Abstraction, ParseFailure
import math
import random
from type import Context, arrow, tint, tlist, UnificationFailure
from data_src.dc_program import generate_IO_examples, compile
from itertools import zip_longest, chain
from functools import reduce
import torch

#from dc_program import Program as dc_Program

def make_deepcoder_data(filename, with_holes=False, size=10000000, k=20):
	data_list = []
	save_freq = 1000

	t = time.time()
	for i in range(size):
		inst = getInstance(with_holes=with_holes, k=k)
		data_list.append(inst)


		if i%save_freq==0:
			#save data
			
			print(f"iteration {i} out of {size}")
			print("saving data")
			with open(filename, 'wb') as file:
				pickle.dump(data_list, file)
			print(f"time since last {save_freq}: {time.time()-t}")
			t = time.time()

#I want a list of namedTuples

#Datum = namedtuple('Datum', ['tp', 'p', 'pseq', 'IO', 'sketch', 'sketchseq'])

class Datum():
	def __init__(self, tp, p, pseq, IO, sketch, sketchseq, reward, sketchprob):
		self.tp = tp
		self.p = p
		self.pseq = pseq
		self.IO = IO
		self.sketch = sketch
		self.sketchseq = sketchseq
		self.reward = reward
		self.sketchprob = sketchprob

	def __hash__(self): 
		return reduce(lambda a, b: hash(a + hash(b)), flatten(self.IO), 0) + hash(self.p) + hash(self.sketch)

Batch = namedtuple('Batch', ['tps', 'ps', 'pseqs', 'IOs', 'sketchs', 'sketchseqs', 'rewards', 'sketchprobs'])

def convert_dc_program_to_ec(dc_program, tp):
	source = dc_program.src
	source = source.split('\n')
	source = [line.split(' ') for line in source]
	#print(source)
	num_inputs = len(tp.functionArguments())
	#print(num_inputs)
	del source[:num_inputs]
	source = [[l for l in line if l != '<-'] for line in source]
	last_var = source[-1][0]
	prog = source[-1][1:]
	del source[-1]
	variables = list('abcdefghigklmnop')
	del variables[variables.index(last_var):] #check this line
	lookup = {variables[i]: ["input_" + str(i)] for i in range(num_inputs)}
	for line in source:
		lookup[line[0]] = line[1:]
	for variable in reversed(variables):
		p2 = []
		for x in prog:
			if x==variable:
				p2 += lookup[variable]
			else:
				p2.append(x)
		prog = p2
	return prog


def convert_source_to_datum(source, N=5, V=512, L=10, compute_sketches=False, top_k_sketches=20, inv_temp=1.0, reward_fn=None, sample_fn=None, dc_model=None, use_timeout=False):
	source = source.replace(' | ', '\n')
	dc_program = compile(source, V=V, L=L)

	if dc_program is None:
		return None
	# find IO
	IO = tuple(generate_IO_examples(dc_program, N=N, L=L, V=V))

	# find tp
	ins = [tint if inp == int else tlist(tint) for inp in dc_program.ins] 
	if dc_program.out == int:
		out = tint
	else:
		assert dc_program.out==[int]
		out = tlist(tint)
	tp = arrow( *(ins+[out]) )

	# find program p
	pseq = tuple(convert_dc_program_to_ec(dc_program, tp))

	# find pseq
	p = parseprogram(pseq, tp)  # TODO: use correct grammar, and 

	if compute_sketches:
		# find sketch

		grammar = basegrammar if not dc_model else dc_model.infer_grammar(IO) #This line needs to change
		sketch, reward, sketchprob = make_holey_deepcoder(p, top_k_sketches, grammar, tp, inv_temp=inv_temp, reward_fn=reward_fn, sample_fn=sample_fn, use_timeout=use_timeout) #TODO

		# find sketchseq
		sketchseq = tuple(flatten_program(sketch))
	else:
		sketch, sketchseq, reward, sketchprob = None, None, None, None

	return Datum(tp, p, pseq, IO, sketch, sketchseq, reward, sketchprob)


def grouper(iterable, n, fillvalue=None):
	"Collect data into fixed-length chunks or blocks"
	# grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
	args = [iter(iterable)] * n
	return zip_longest(*args, fillvalue=fillvalue)

def single_batchloader(data_file, batchsize=100, N=5, V=512, L=10, compute_sketches=False, dc_model=None, shuffle=True, top_k_sketches=20, inv_temp=1.0, reward_fn=None, sample_fn=None, use_timeout=False):
	lines = (line.rstrip('\n') for i, line in enumerate(open(data_file)) if i != 0) #remove first line
	if shuffle:
		lines = list(lines)
		random.shuffle(lines)

	if batchsize==1:
		data = (convert_source_to_datum(line, N=N, V=V, L=L, compute_sketches=compute_sketches, dc_model=dc_model, top_k_sketches=20, inv_temp=inv_temp, reward_fn=reward_fn, sample_fn=sample_fn, use_timeout=use_timeout) for line in lines)
		yield from (x for x in data if x is not None)
	else:
		data = (convert_source_to_datum(line, N=N, V=V, L=L, compute_sketches=compute_sketches, dc_model=dc_model, top_k_sketches=20, inv_temp=inv_temp, reward_fn=reward_fn, sample_fn=sample_fn, use_timeout=use_timeout) for line in lines)
		data = (x for x in data if x is not None)
		grouped_data = grouper(data, batchsize)

		for group in grouped_data:
			tps, ps, pseqs, IOs, sketchs, sketchseqs, rewards, sketchprobs = zip(*[(datum.tp, datum.p, datum.pseq, datum.IO, datum.sketch, datum.sketchseq, datum.reward, datum.sketchprob) for datum in group if datum is not None])
			yield Batch(tps, ps, pseqs, IOs, sketchs, sketchseqs, torch.FloatTensor(rewards) if any(r is not None for r in rewards) else None, torch.FloatTensor(sketchprobs) if any(s is not None for s in sketchprobs) else None)  # check that his works 

def batchloader(data_file_list, batchsize=100, N=5, V=512, L=10, compute_sketches=False, dc_model=None, shuffle=True, top_k_sketches=20, inv_temp=1.0, reward_fn=None, sample_fn=None, use_timeout=False):
	yield from chain(*[single_batchloader(data_file, batchsize=batchsize, N=N, V=V, L=L, compute_sketches=compute_sketches, dc_model=dc_model, shuffle=shuffle, top_k_sketches=top_k_sketches, inv_temp=inv_temp, reward_fn=reward_fn, sample_fn=sample_fn, use_timeout=use_timeout) for data_file in data_file_list])


if __name__=='__main__':
	from itertools import islice
	#convert_source_to_datum("a <- [int] | b <- [int] | c <- ZIPWITH + b a | d <- COUNT isEVEN c | e <- ZIPWITH MAX a c | f <- MAP MUL4 e | g <- TAKE d f")

	#filename = 'data/DeepCoder_data/T2_A2_V512_L10_train_perm.txt'
	train_data = 'data/DeepCoder_data/T3_A2_V512_L10_train_perm.txt'

	#test_data = ''

	#lines = (line.rstrip('\n') for i, line in enumerate(open(filename)) if i != 0) #remove first line

	from util.deepcoder_util import grammar

	import models.deepcoderModel as deepcoderModel
	dcModel = torch.load("./saved_models/dc_model.p")

	for datum in islice(batchloader([train_data], batchsize=1, N=5, V=128, L=10, compute_sketches=True, top_k_sketches=20, inv_temp=0.25, use_timeout=True), 1):

		print("program:", datum.p)
		print("sketch: ", datum.sketch)
		grammar = dcModel.infer_grammar(datum.IO)
		l = grammar.sketchLogLikelihood(datum.tp, datum.p, datum.sketch)
		print(l)


		# 

		# p,_,_ = make_holey_deepcoder(datum.p, 50, grammar, datum.tp, inv_temp=1.0, reward_fn=None, sample_fn=None, verbose=True)
		# print("SKETCH:",p)
		# p,_,_ = make_holey_deepcoder(datum.p, 50, grammar, datum.tp, inv_temp=1.0, reward_fn=None, sample_fn=None, verbose=True, use_timeout=True)
		# print("SKETCH:",p)

		# p,_,_ = make_holey_deepcoder(datum.p, 50, grammar, datum.tp, inv_temp=0.5, reward_fn=None, sample_fn=None, verbose=True)
		# print("SKETCH:",p)
		# p,_,_ = make_holey_deepcoder(datum.p, 50, grammar, datum.tp, inv_temp=0.5, reward_fn=None, sample_fn=None, verbose=True, use_timeout=True)
		# print("SKETCH:",p)

		# p,_,_ = make_holey_deepcoder(datum.p, 50, grammar, datum.tp, inv_temp=0.25, reward_fn=None, sample_fn=None, verbose=True)
		# print("SKETCH:",p)
		# p,_,_ = make_holey_deepcoder(datum.p, 50, grammar, datum.tp, inv_temp=0.25, reward_fn=None, sample_fn=None, verbose=True, use_timeout=True)
		# print("SKETCH:",p)

	#path = 'data/pretrain_data_v1_alt.p'
	#make_deepcoder_data(path, with_holes=True, k=20)




