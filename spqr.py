'''
Author: Yotam Gingold <yotam (strudel) yotamgingold.com>
License: Public Domain [CC0](http://creativecommons.org/publicdomain/zero/1.0/)
Description: Wrapper for SuiteSparse qr() function. Matlab has it, Python should have it, too.
'''

from __future__ import print_function, division

try:
    from _spqr import ffi, lib
except ImportError:
    print( "=== Wrapper module not compiled; compiling..." )
    import spqr_gen
    spqr_gen.main()
    print( "=== ...compiled." )
    
    from _spqr import ffi, lib

import scipy.sparse
import numpy

'''
Helpful links:
    The primary docs:
    http://cffi.readthedocs.io/en/latest/overview.html
    http://cffi.readthedocs.io/en/latest/using.html
    
    Some helpful examples for #define and NumPy:
    https://kogs-www.informatik.uni-hamburg.de/~seppke/content/teaching/wise1314/20131107_pridoehl-cffi.pdf
'''

## Initialize cholmod
cc = ffi.new("cholmod_common*")
lib.cholmod_l_start( cc )

def deinit():
    lib.cholmod_l_finish( cc )

def scipy2choldmod( scipy_A ):
    scipy_A = scipy_A.tocoo()
    
    nnz = scipy_A.nnz
    
    ## There is a potential performance win if we know A is symmetric and we
    ## can get only the upper or lower triangular elements.
    chol_A = lib.cholmod_l_allocate_triplet( scipy_A.shape[0], scipy_A.shape[1], nnz, 0, lib.CHOLMOD_REAL, cc )
    
    Ai = ffi.cast( "SuiteSparse_long*", chol_A.i )
    Aj = ffi.cast( "SuiteSparse_long*", chol_A.j )
    Avals = ffi.cast( "double*", chol_A.x )
    
    Ai[0:nnz] = scipy_A.row
    Aj[0:nnz] = scipy_A.col
    Avals[0:nnz] = scipy_A.data
    
    chol_A.nnz = nnz
    
    lib.cholmod_l_print_triplet( chol_A, "A", cc )
    assert lib.cholmod_l_check_triplet( chol_A, cc ) == 1
    
    ## Convert to a cholmod_sparse matrix.
    result = lib.cholmod_l_triplet_to_sparse( chol_A, nnz, cc )
    ## Free the space used by the cholmod triplet matrix.
    cholmod_free_triplet( chol_A )
    
    return result

def cholmod2scipy( chol_A ):
    ## Convert to a cholmod_triplet matrix.
    chol_A = lib.cholmod_l_sparse_to_triplet( chol_A, cc )
    
    nnz = chol_A.nnz
    
    i = numpy.zeros( nnz, dtype = numpy.int64 )
    j = numpy.zeros( nnz, dtype = numpy.int64 )
    data = numpy.zeros( nnz )
    
    Ai = ffi.cast( "SuiteSparse_long*", chol_A.i )
    Aj = ffi.cast( "SuiteSparse_long*", chol_A.j )
    Adata = ffi.cast( "double*", chol_A.x )
    
    ## Have to pass through list.
    ## https://bitbucket.org/cffi/cffi/issues/292/cant-copy-data-to-a-numpy-array
    ## http://stackoverflow.com/questions/16276268/how-to-pass-a-numpy-array-into-a-cffi-function-and-how-to-get-one-back-out
    i[0:nnz] = list( Ai[0:nnz] )
    j[0:nnz] = list( Aj[0:nnz] )
    data[0:nnz] = list( Adata[0:nnz] )
    
    scipy_A = scipy.sparse.coo_matrix(
        ( data, ( i, j ) ),
        shape = ( chol_A.nrow, chol_A.ncol )
        )
    
    ## Free the space used by the cholmod triplet matrix.
    cholmod_free_triplet( chol_A )
    
    return scipy_A

def cholmod_free_triplet( A ):
    A_ptr = ffi.new("cholmod_triplet**")
    A_ptr[0] = A
    lib.cholmod_l_free_triplet( A_ptr, cc )

def qr( A ):
    '''
    Given a sparse matrix A,
    returns Q, R, E, rank such that:
        Q*R = A*permutation_from_E(E)
    rank is the estimated rank of A.
    '''
    
    chol_A = scipy2choldmod( A )
    
    chol_Q = ffi.new("cholmod_sparse**")
    chol_R = ffi.new("cholmod_sparse**")
    chol_E = ffi.new("SuiteSparse_long**")
    
    rank = lib.SuiteSparseQR_C_QR(
        ## Input
        lib.SPQR_ORDERING_DEFAULT,
        lib.SPQR_DEFAULT_TOL,
        A.shape[0],
        chol_A,
        ## Output
        chol_Q,
        chol_R,
        chol_E,
        cc
        )
    
    scipy_Q = cholmod2scipy( chol_Q[0] )
    scipy_R = cholmod2scipy( chol_R[0] )
    
    ## If chol_E is null, there was no permutation.
    if chol_E == ffi.NULL:
        E = None
    else:
        E = numpy.zeros( A.shape[1], dtype = int )
        ## Have to pass through list.
        ## https://bitbucket.org/cffi/cffi/issues/292/cant-copy-data-to-a-numpy-array
        ## http://stackoverflow.com/questions/16276268/how-to-pass-a-numpy-array-into-a-cffi-function-and-how-to-get-one-back-out
        E[0:A.shape[1]] = list( chol_E[0][0:A.shape[1]] )
    
    ## Free cholmod stuff
    lib.cholmod_l_free_sparse( chol_Q, cc )
    lib.cholmod_l_free_sparse( chol_R, cc )
    ## Apparently we don't need to do this. (I get a malloc error.)
    # lib.cholmod_l_free( A.shape[1], ffi.sizeof("SuiteSparse_long"), chol_E, cc )
    
    return scipy_Q, scipy_R, E, rank

def permutation_from_E( E ):
    n = len( E )
    j = numpy.arange( n )
    return scipy.sparse.coo_matrix( ( numpy.ones(n), ( E, j ) ), shape = ( n, n ) )

if __name__ == '__main__':
    # Q, R, E, rank = qr( scipy.sparse.identity(10) )
    
    M = scipy.sparse.rand( 10, 10, density = 0.1 )
    Q, R, E, rank = qr( M )
    print( abs( Q*R - M*permutation_from_E(E) ).sum() )