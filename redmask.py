#!/usr/bin/env python

import sys
import os
import argparse
import datetime
import platform
import subprocess
import shutil
from Bio import SeqIO
from natsort import natsorted

__version__ = "0.0.1"
#setup menu with argparse
class MyFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def __init__(self, prog):
        super(MyFormatter, self).__init__(prog, max_help_position=48)
parser = argparse.ArgumentParser(prog='redmask.py',
    description = '''Wraper for Red - repeat identification and masking for genome annotation''',
    epilog = """Written by Jon Palmer (2018) nextgenusfs@gmail.com""",
    formatter_class = MyFormatter)
parser.add_argument('-i', '--genome', required=True, help='genome assembly FASTA format')
parser.add_argument('-o', '--output', required=True, help='Output basename')
parser.add_argument('-m', '--min', default=3, type=int, help='Minimum number of observed k-mers')
parser.add_argument('-t', '--training', default=1000, type=int, help='Min length for training')
parser.add_argument('--version', action='version', version='%(prog)s v{version}'.format(version=__version__))
args=parser.parse_args()

def which_path(file_name):
    for path in os.environ["PATH"].split(os.pathsep):
        full_path = os.path.join(path, file_name)
        if os.path.exists(full_path) and os.access(full_path, os.X_OK):
            return full_path
    return None
    
#via https://stackoverflow.com/questions/2154249/identify-groups-of-continuous-numbers-in-a-list
def group(L):
    if len(L) < 1:
        return
    first = last = L[0]
    for n in L[1:]:
        if n - 1 == last: # Part of the group, bump the end
            last = n
        else: # Not part of the group, yield current group and start a new
            yield first, last
            first = last = n
    yield first, last # Yield the last group

def n_lower_chars(string):
    return sum(1 for c in string if c.islower())

def n50(input):
    lengths = []
    with open(input, 'rU') as infile:
        for rec in SeqIO.parse(infile, 'fasta'):
            lengths.append(len(rec.seq))
    lengths.sort()
    nlist = []
    for x in lengths:
        nlist += [x]*x
    if len(nlist) % 2 == 0:
        medianpos = int(len(nlist) / 2)
        N50 = int((nlist[medianpos] + nlist[medianpos-1]) / 2)
    else:
        medianpos = int(len(nlist) / 2)
        N50 = int(nlist[medianpos])
    return N50

def SafeRemove(input):
    if os.path.isdir(input):
        shutil.rmtree(input)
    elif os.path.isfile(input):
        os.remove(input)
    else:
        return

sys.stdout.write('[{:}] Running Python v{:} \n'.format(datetime.datetime.now().strftime('%b %d %I:%M %p'), platform.python_version()))
dependencies = ['Red']
for x in dependencies:
    if not which_path(x):
        print('{:} is not properly installed, install and re-run script'.format(x))
        sys.exit(1)

pid = os.getpid()
inputDir = 'redmask_contigs_'+str(pid)
trainDir = 'redmask_train_'+str(pid)
outputDir = 'redmask_output_'+str(pid)
logfile = 'redmask_'+str(pid)+'.log'
if os.path.isfile(logfile):
    os.remove(logfile)
os.makedirs(inputDir)
os.makedirs(outputDir)
os.makedirs(trainDir)

with open(logfile, 'w') as log:
    calcN50 = n50(args.genome)
    sys.stdout.write('[{:}] Loading assembly with N50 of {:,} bp\n'.format(datetime.datetime.now().strftime('%b %d %I:%M %p'), calcN50))
    sys.stdout.write('[{:}] Splitting genome assembly into training set (contigs > N50)\n'.format(datetime.datetime.now().strftime('%b %d %I:%M %p')))
    with open(args.genome, 'rU') as input:
        for rec in SeqIO.parse(input, 'fasta'):
            if len(rec.seq) >= args.training: #calcN50:
                with open(os.path.join(trainDir,rec.id+'.fa'), 'w') as output:
                    SeqIO.write(rec, output, 'fasta')
            else:
                with open(os.path.join(inputDir,rec.id+'.fa'), 'w') as output:
                    SeqIO.write(rec, output, 'fasta')
    sys.stdout.write('[{:}] Finding repeats with Red (REpeat Detector)\n'.format(datetime.datetime.now().strftime('%b %d %I:%M %p')))
    cmd = ['Red', '-gnm', trainDir, '-dir', inputDir, '-sco', outputDir, '-min', str(args.min), '-msk', outputDir]
    subprocess.call(cmd, stdout=log, stderr=log)
    
    sys.stdout.write('[{:}] Collecting results from Red\n'.format(datetime.datetime.now().strftime('%b %d %I:%M %p')))
    maskedOut = args.output+'.softmasked.fa'
    maskedfiles = []
    for file in os.listdir(outputDir):
        if file.endswith('.msk'):
            maskedfiles.append(os.path.join(outputDir, file))
    with open(maskedOut, 'w') as outfile:
        for fname in natsorted(maskedfiles):
            with open(fname) as infile:
                for line in infile:
                    outfile.write(line)
    
    sys.stdout.write('[{:}] Summarizing results and converting to BED format\n'.format(datetime.datetime.now().strftime('%b %d %I:%M %p')))
    maskedBED = args.output+'.repeats.bed'
    maskedFA = args.output+'.repeats.fasta'
    #load contig names and sizes into dictionary, get masked repeat stats
    GenomeLength = 0
    maskedSize = 0
    masked = {}
    with open(maskedOut, 'rU') as input:
        for rec in SeqIO.parse(input, 'fasta'):
            if not rec.id in masked:
                masked[rec.id] = []
            Seq = str(rec.seq)
            GenomeLength += len(Seq)
            maskedSize += n_lower_chars(Seq)
            for i,c in enumerate(Seq):
                if c.islower():
                    masked[rec.id].append(i) #0 based
    counter = 1
    SeqRecords = SeqIO.to_dict(SeqIO.parse(maskedOut, "fasta"))
    with open(maskedBED, 'w') as bedout:
        with open(maskedFA, 'w') as faout:   
            for k,v in natsorted(masked.items()):
                repeats = list(group(v))
                for item in repeats:
                    if len(item) == 2:
                        bedout.write('{:}\t{:}\t{:}\tRepeat_{:}\n'.format(k,item[0], item[1], counter))
                        faout.write('>Repeat_{:} {:}\n{:}\n'.format(counter, k, SeqRecords[k][int(item[0]):int(item[1])].seq))
                        counter += 1

    percentMask = maskedSize / float(GenomeLength)
    sys.stdout.write('\nMasked genome: {:}\nnum scaffolds: {:,}\nassembly size: {:,} bp\nmasked repeats: {:,} bp ({:.2f}%)\n\n'.format(os.path.abspath(maskedOut), len(masked), GenomeLength, maskedSize, percentMask*100))

#clean up
SafeRemove(inputDir)
SafeRemove(trainDir)
SafeRemove(outputDir)