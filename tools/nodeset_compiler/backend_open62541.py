#!/usr/bin/env/python
# -*- coding: utf-8 -*-

###
### Author:  Chris Iatrou (ichrispa@core-vector.net)
### Version: rev 13
###
### This program was created for educational purposes and has been
### contributed to the open62541 project by the author. All licensing
### terms for this source is inherited by the terms and conditions
### specified for by the open62541 project (see the projects readme
### file for more information on the LGPL terms and restrictions).
###
### This program is not meant to be used in a production environment. The
### author is not liable for any complications arising due to the use of
### this program.
###

from __future__ import print_function
import string
from collections import deque
from os.path import basename
import logging

logger = logging.getLogger(__name__)

from constants import *
from nodes import *
from nodeset import *
from backend_open62541_nodes import generateNodeCode, generateReferenceCode

##############
# Sort Nodes #
##############

# Select the references that shall be generated after this node in the ordering
def selectPrintRefs(nodeset, L, node):
    printRefs = []
    for ref in node.references:
        if ref.hidden:
            continue
        targetnode = nodeset.nodes[ref.target]
        if not targetnode in L:
            continue
        printRefs.append(ref)
    for ref in node.inverseReferences:
        if ref.hidden:
            continue
        targetnode = nodeset.nodes[ref.target]
        if not targetnode in L:
            continue
        printRefs.append(ref)
    return printRefs

def reorderNodesMinDependencies(nodeset):
    # Kahn's algorithm
    # https://algocoding.wordpress.com/2015/04/05/topological-sorting-python/

    relevant_types = getSubTypesOf(nodeset,
                                   nodeset.getNodeByBrowseName("HierarchicalReferences"))
    relevant_types = map(lambda x: x.id, relevant_types)

    # determine in-degree
    in_degree = {u.id: 0 for u in nodeset.nodes.values()}
    for u in nodeset.nodes.values():  # of each node
        for ref in u.references:
            if (ref.referenceType in relevant_types and ref.isForward):
                in_degree[ref.target] += 1

    # collect nodes with zero in-degree
    Q = deque()
    for id in in_degree:
        if in_degree[id] == 0:
            # print referencetypenodes first
            n = nodeset.nodes[id]
            if isinstance(n, ReferenceTypeNode):
                Q.append(nodeset.nodes[id])
            else:
                Q.appendleft(nodeset.nodes[id])

    L = []  # list for order of nodes
    while Q:
        u = Q.pop()  # choose node of zero in-degree
        # decide which references to print now based on the ordering
        u.printRefs = selectPrintRefs(nodeset, L, u)
        L.append(u)  # and 'remove' it from graph
        for ref in u.references:
            if (ref.referenceType in relevant_types and ref.isForward):
                in_degree[ref.target] -= 1
                if in_degree[ref.target] == 0:
                    Q.append(nodeset.nodes[ref.target])
    if len(L) != len(nodeset.nodes.values()):
        raise Exception("Node graph is circular on the specified references")
    return L

###################
# Generate C Code #
###################

def generateOpen62541Code(nodeset, outfilename, supressGenerationOfAttribute=[], generate_ns0=False):
    outfilebase = basename(outfilename)
    # Printing functions
    outfileh = open(outfilename + ".h", r"w+")
    outfilec = open(outfilename + ".c", r"w+")

    def writeh(line):
        print(unicode(line).encode('utf8'), end='\n', file=outfileh)

    def writec(line):
        print(unicode(line).encode('utf8'), end='\n', file=outfilec)

    # Print the preamble of the generated code
    writeh("""/* WARNING: This is a generated file.
 * Any manual changes will be overwritten. */

#ifndef %s_H_
#define %s_H_

#ifdef UA_NO_AMALGAMATION
#include "ua_types.h"
#include "ua_job.h"
#include "ua_server.h"
#else
#include "open62541.h"
#define NULL ((void *)0)
#endif
    
extern void %s(UA_Server *server);

#endif /* %s_H_ */""" % \
           (outfilebase.upper(), outfilebase.upper(),
            outfilebase, outfilebase.upper()))

    writec("""/* WARNING: This is a generated file.
 * Any manual changes will be overwritten. */

#include "%s.h"

void %s(UA_Server *server) {""" % (outfilebase, outfilebase))

    parentrefs = getSubTypesOf(nodeset, nodeset.getNodeByBrowseName("HierarchicalReferences"))
    parentrefs = map(lambda x: x.id, parentrefs)

    # Generate namespaces (don't worry about duplicates)
    writec("/* Use namespace ids generated by the server */")
    for i, nsid in enumerate(nodeset.namespaces):
        nsid = nsid.replace("\"", "\\\"")
        writec("UA_UInt16 ns" + str(i) + " = UA_Server_addNamespace(server, \"" + nsid + "\");")

    # Loop over the sorted nodes
    logger.info("Reordering nodes for minimal dependencies during printing")
    sorted_nodes = reorderNodesMinDependencies(nodeset)
    logger.info("Writing code for nodes and references")
    for node in sorted_nodes:
        # Print node
        if not node.hidden:
            writec("\n/* " + str(node.displayName) + " - " + str(node.id) + " */")
            writec(generateNodeCode(node, supressGenerationOfAttribute, generate_ns0, parentrefs))

        # Print inverse references leading to this node
        for ref in node.printRefs:
            writec(generateReferenceCode(ref))

    # Finalize the generated source
    writec("} // closing nodeset()")
    outfileh.close()
    outfilec.close()
