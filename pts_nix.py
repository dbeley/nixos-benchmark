# Minimal Phoronix Test Suite reimplementation for NixOS
# Supports phpbench, 7zip and openssl benchmarks
import argparse
import os
import re
import subprocess
import tarfile
import shutil
import urllib.request
import json

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, 'cache')
RESULTS = os.path.join(ROOT, 'results')

os.makedirs(CACHE, exist_ok=True)
os.makedirs(RESULTS, exist_ok=True)

class Benchmark:
    name: str

    def download(self, url: str, dest: str):
        if not os.path.exists(dest):
            print(f'Downloading {url}')
            urllib.request.urlretrieve(url, dest)

    def run_cmd(self, cmd, log_file, cwd=None):
        print('Running', ' '.join(cmd))
        with open(log_file, 'w') as f:
            subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, check=False)

class PhpBench(Benchmark):
    name = 'phpbench'
    url = 'http://download.pureftpd.org/pub/phpbench/phpbench-0.8.1.tar.gz'
    archive = os.path.join(CACHE, 'phpbench-0.8.1.tar.gz')
    src_dir = os.path.join(CACHE, 'phpbench-0.8.1')

    def install(self):
        if not os.path.isdir(self.src_dir):
            self.download(self.url, self.archive)
            with tarfile.open(self.archive, 'r:gz') as t:
                t.extractall(CACHE)

    def run(self):
        self.install()
        log = os.path.join(RESULTS, 'phpbench.log')
        self.run_cmd(['php', os.path.join(self.src_dir, 'phpbench.php')], log)
        return self.parse(log)

    def parse(self, log):
        with open(log) as f:
            for line in f:
                m = re.search(r'Score\s*:\s*(\d+(?:\.\d+)?)', line)
                if m:
                    return float(m.group(1))
        return None

class SevenZip(Benchmark):
    name = '7zip'

    def run(self):
        log = os.path.join(RESULTS, '7zip.log')
        # Uses system 7z binary
        cmd = ['7za', 'b'] if shutil.which('7za') else ['7z', 'b']
        self.run_cmd(cmd, log)
        return self.parse(log)

    def parse(self, log):
        rating = None
        with open(log) as f:
            for line in f:
                if line.strip().startswith('Avr:'):
                    parts = line.split()
                    # compression rating field
                    try:
                        rating = float(parts[4])
                    except (IndexError, ValueError):
                        pass
        return rating

class OpenSSLBench(Benchmark):
    name = 'openssl'

    def run(self):
        log = os.path.join(RESULTS, 'openssl.log')
        self.run_cmd(['openssl', 'speed', 'rsa4096'], log)
        return self.parse(log)

    def parse(self, log):
        with open(log) as f:
            for line in f:
                if '4096 bits' in line:
                    parts = line.split()
                    try:
                        return float(parts[-2])
                    except (IndexError, ValueError):
                        pass
        return None

def main():
    tests = {
        'phpbench': PhpBench(),
        '7zip': SevenZip(),
        'openssl': OpenSSLBench(),
    }

    parser = argparse.ArgumentParser(description='Minimal PTS-like benchmark runner')
    parser.add_argument('benchmarks', nargs='*', default=list(tests.keys()), help='Benchmarks to run')
    args = parser.parse_args()

    results = {}
    for name in args.benchmarks:
        if name not in tests:
            print(f'Unknown benchmark: {name}')
            continue
        score = tests[name].run()
        results[name] = score
        print(f'{name}: {score}')

    with open(os.path.join(RESULTS, 'summary.json'), 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    main()
