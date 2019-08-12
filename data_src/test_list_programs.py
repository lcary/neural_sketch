import sys
import os
sys.path.append(os.path.abspath('..'))
from data_src.dc_program import test_program, generate_IO_examples
from data_src.dc_program import compile as compile_program


def test_sample(sample, program, debug=False):
    if debug:
        print('input:  ', sample[0])
        print('expect: ', sample[1])
        print('actual: ', program.fun(sample[0]))
    assert program.fun(sample[0]) == sample[1]


def test_sum_top_index_sorted():
    source = 'a <- int | b <- [int] | c <- SORT b | d <- TAKE a c | e <- SUM d'
    program = test_program(source, N=10)
    sample = ((2, [3, 5, 4, 7, 5]), 7)
    test_sample(sample, program)


def test_head_tail():
    source = 'a <- [int] | b <- HEAD a'
    program = test_program(source, N=10)
    sample = (([3, 5, 4, 7, 5],), 3)
    test_sample(sample, program)

    source = 'a <- [int] | b <- TAIL a'
    program = test_program(source, N=10)
    sample = (([3, 5, 4, 7, 5],), [5, 4, 7, 5])
    test_sample(sample, program)


def test_count_head_in_tail():
    # src1 = 'count (head xs) (tail xs)'
    source = 'a <- [int] | b <- TAIL a | c <- HEAD a | d <- COUNT c b'
    program = test_program(source, N=10)
    sample = (([3, 5, 4, 7, 5],), 0)
    test_sample(sample, program)
    sample = (([5, 4, 7, 5],), 1)
    test_sample(sample, program)
    sample = (([7, 4, 7, 8, 21, 1, 7, 2, 7, 5],), 3)
    test_sample(sample, program)


def some_differ(samples):
    outputs = [p[-1] for p in samples]
    if not outputs:
        raise ValueError("No outputs returned! Error generating IO pairs.")
    i0 = outputs[0]
    return any(i != i0 for i in outputs)


def generate_interesting_io_examples(source, N=5, timeout=10):
    import time
    t = time.time()
    source = source.replace(' | ', '\n')
    program = compile_program(source, V=512, L=10)
    all_same_outputs = True
    elapsed = time.time() - t
    samples = []
    while all_same_outputs and elapsed < timeout:
        samples = generate_IO_examples(program, N=N, L=10, V=512)
        elapsed = time.time() - t
        if some_differ(samples):
            all_same_outputs = False
    print(("time:", elapsed))
    print(program)
    if all_same_outputs:
        print('No interesting samples.')
    print('samples:')
    for s in samples:
        print('    {}'.format(s))
    return program


# TODO: can't find interesting examples of outputs since maxv is less than list length!
def test_count_len_in_tail():
    # src2 = 'count (len xs) (tail xs)'
    source = 'a <- [int] | b <- TAIL a | c <- LEN a | d <- COUNT c b'
    program = generate_interesting_io_examples(source, N=10)
    sample = (([3, 5, 4, 7, 5],), 2)
    test_sample(sample, program)
    sample = (([5, 4, 7, 5],), 1)
    test_sample(sample, program)
    sample = (([7, 4, 7, 8, 21, 1, 7, 2, 7, 5],), 0)
    test_sample(sample, program)


if __name__ == '__main__':
    # test_sum_top_index_sorted()
    # test_head_tail()
    test_count_head_in_tail()
    test_count_len_in_tail()
