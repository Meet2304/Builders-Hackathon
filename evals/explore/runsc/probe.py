"""Compare the same executable on native Linux and gVisor inside Docker.

The image must contain /usr/bin/time. Install the official arm64 gVisor bundle
on the host and point --gvisor at its extracted directory (including gvisor-bin).
Each invocation stages the dataset into a unique Docker volume outside the
measurement interval. JSON lines include both in-sandbox and outer wall times.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

def docker(*args, timeout=100):
    return subprocess.run(["docker", *map(str,args)], capture_output=True,
                          text=True, check=True, timeout=timeout).stdout

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--gvisor", type=Path, required=True)
    parser.add_argument("--pairs", type=int, choices=range(1,7), default=3)
    parser.add_argument("--binary", default="/app/sessions")
    parser.add_argument("--env", action="append", default=[])
    args = parser.parse_args()
    token = "critpath-" + uuid.uuid4().hex[:12]
    lock = Path("/tmp/builders-bench.lock")
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            time.sleep(60)
    def interrupt(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    owner = lock / "owner"
    owner.write_text(f"pid={os.getpid()}\nbranch=explore/critpath\n")
    try:
        docker("volume", "create", token)
        docker("run","--rm","--network","none","-v",f"{args.data.resolve()}:/input:ro",
               "-v",f"{token}:/data",args.image,"cp","-r","/input/.","/data/")
        flags = ["run","--rm","--name",token,"--platform","linux/arm64","--privileged",
                 "--network","none","--memory","22g","--memory-swap","22g","--cpus","8",
                 "--pids-limit","4096","-v",f"{token}:/data:ro","--tmpfs","/output:mode=1777",
                 "-v",f"{args.gvisor.resolve()}:/gv:ro"]
        sha = docker("run","--rm",args.image,"sha256sum",args.binary).split()[0]
        start = time.monotonic()
        for i in range(args.pairs):
            for mode in (["plain","runsc"] if i % 2 == 0 else ["runsc","plain"]):
                if time.monotonic() - start > 440:
                    raise RuntimeError("ending lock window before next run")
                command = ["env","NCPU=8",*args.env,"/usr/bin/time","-f",
                           "sample %e %U %S %R %F %x",args.binary]
                if mode == "runsc":
                    command = ["/gv/runsc","--ignore-cgroups","--rootless","--network=none",
                               "do","-volume","/data:/data","-volume","/output:/output",*command]
                # The outer Linux clock includes runsc create and destroy, excluding Docker launch.
                script = 's=$(date +%s%N); "$@"; rc=$?; e=$(date +%s%N); echo outer_ns=$((e-s)); exit $rc'
                run = subprocess.run(["docker",*flags,args.image,"sh","-c",script,"sh",*command],
                                     capture_output=True,text=True,timeout=90)
                output = run.stdout + run.stderr
                sample = re.search(r"^sample ([\d.]+) ([\d.]+) ([\d.]+) (\d+) (\d+) (\d+)$",output,re.M)
                if run.returncode or not sample:
                    raise RuntimeError(output)
                wall,user,kernel,minor,major,rc = sample.groups()
                print(json.dumps(dict(iteration=i,mode=mode,sha256=sha,image=args.image,
                                      dataset=args.data.name,wall_s=float(wall),user_s=float(user),
                                      system_s=float(kernel),minor=int(minor),major=int(major),
                                      outer_s=int(re.search(r"outer_ns=(\d+)",output)[1])/1e9,
                                      stderr=run.stderr,env=args.env)),flush=True)
    finally:
        subprocess.run(["docker","rm","-f",token],capture_output=True)
        subprocess.run(["docker","volume","rm",token],capture_output=True)
        owner.unlink(missing_ok=True)
        lock.rmdir()

if __name__ == "__main__":
    main()
