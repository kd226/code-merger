import os
import argparse
import re
import glob
import logging

FORMAT = '%(levelname)s: %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger()

def is_source_file(fname):
    return fname.endswith(('.cpp', '.c'))

def is_header_file(fname):
    return fname.endswith(('.hpp', '.h'))

class FileText:
    def __init__(self, fname, dir):
        self.fname = fname
        self.name = os.path.basename(fname)
        self.path = os.path.abspath(os.path.join(dir, fname))
        self.text = None

        if is_header_file(fname):
            self.type = 'header'
        elif is_source_file(fname):
            self.type = 'source'
        else:
            self.type = 'other'
        self.matches = None


    def read(self):
        if self.text is None:
            with open(self.path, 'r') as f:
                self.text = f.read()

        return self.text

    def parse(self):
        if self.matches is None:
            text = self.read()
            self.matches = []
            include_regex = r'#include\s*[<"]([\w/\.]+)[>"]\s*\n'
            regex = re.compile(include_regex)
            start = 0
            matched = True
            while matched:
                match = regex.search(text, start)
                if match:
                    self.matches.append((match.group(0), match.group(1)))
                    start = match.end()
                else:
                    matched = False
        return self.matches

class FileManager:
    def __init__(self, files, dir):
        parsed_files = [FileText(fn, dir) for fn in files]
        self.source_files = [pf for pf in parsed_files if pf.type == 'source']
        self.header_files = [pf for pf in parsed_files if pf.type != 'source']

class Merger:
    def __init__(self, main):
        self.main = main

    def merge_guard(self, headers, included_depth, included_all):
        matches = self.main.parse()
        main_text = self.main.read()
        included_all |= {self.main.name}
        for match, inc_file in matches:
            if inc_file in included_depth:
                ## Present in current include path
                logger.error("Recursive include detected in " + self.main.name + " on header " + inc_file + ". Replacing by empty.")
                main_text = main_text.replace(match, "", 1)
            elif inc_file in included_all:
                ## Already included above
                main_text = main_text.replace(match, "", 1)
            else:
                replaced = False
                for header in headers:
                    if header.name == inc_file:
                        tmp_merger = Merger(header)
                        replace_text = tmp_merger.merge_guard(headers, included_depth | {self.main.name}, included_all)
                        main_text = main_text.replace(match, replace_text, 1)
                        replaced = True
                        break
                if not replaced:
                    logger.warning("Could not inline header: " + inc_file)
                    included_all |= {inc_file}
        return main_text

    def merge(self, headers):
        return self.merge_guard(headers, set(), set())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Inline headers (.hpp, .h) files into source files (.cpp, .h).')
    parser.add_argument('files', nargs='*', type=str, help='files to merge')
    parser.add_argument('--out_dir', '-o', type=str, default='merged/', help='output directory')
    parser.add_argument('--in_dir', '-i', type=str, default='./', help='input directory')
    parser.add_argument('--auto', '-a', action='store_const', default=False, const=True,
                        help='automatically search for files in input directory')
    parser.add_argument('--source_inline', '-s', action='store_const', default=False, const=True,
                        help='inline source files (.cpp, .c)')
    parser.add_argument('--verbosity', '-v', action='count', default=0, help='increase verbosity level (up to 3)')
    arguments = parser.parse_args()

    ## Logging settings
    verbosity = arguments.verbosity
    if verbosity == 0:
        logger.setLevel('ERROR')
    elif verbosity == 1:
        logger.setLevel('WARNING')
    elif verbosity == 2:
        logger.setLevel('INFO')
    else:
        logger.setLevel('DEBUG')

    files = arguments.files
    in_dir = arguments.in_dir
    out_dir = os.path.abspath(arguments.out_dir)

    if arguments.auto:
        ## Auto find files
        r_files = glob.glob(in_dir + '/**/*', recursive=True)
        r_paths = [p[len(in_dir) + len(os.path.sep):] for p in r_files]
        files.extend(r_paths)

    fm = FileManager(files, in_dir)
    if arguments.source_inline:
        to_inline = fm.header_files + fm.source_files
    else:
        to_inline = fm.header_files

    logger.info("Target (source) files: " + str([f.fname for f in fm.source_files]))
    logger.info("Include (header) files: " + str([f.fname for f in to_inline]))
    for sf in fm.source_files:
        logger.info("Begginging merge for: " + sf.fname)
        merger = Merger(sf)
        new_text = merger.merge(to_inline)

        out_path = os.path.abspath(os.path.join(out_dir, sf.fname))
        out_directory = os.path.split(out_path)[0]
        if not os.path.exists(out_directory):
            os.makedirs(out_directory)
        with open(out_path, 'w') as f:
            f.write(new_text)



