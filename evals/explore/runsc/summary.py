"""Print an immediate sample summary and a table of median phase durations."""
import collections
import json
import re
import statistics
import sys

samples = collections.defaultdict(list)
for line in sys.stdin:
    run = json.loads(line)
    mode = run["mode"]
    print(f"{mode:5} process {run['wall_s']:.3f}s, outer {run['outer_s']:.3f}s, "
          f"minor/major {run['minor']}/{run['major']}, sha256 {run['sha256']}")
    phases = {}
    previous = 0.0
    for match in re.finditer(r"^\[\s*([\d.]+)s\] (.*?) \(", run["stderr"], re.M):
        current = float(match[1])
        phases[match[2]] = (current - previous) * 1000
        previous = current
    phases["start and exit outside marks"] = 1000 * (run["wall_s"] - previous)
    phases["process total"] = 1000 * run["wall_s"]
    samples[mode].append(phases)

if samples["plain"] and samples["runsc"]:
    print("Phase                                      plain ms    runsc ms    delta ms")
    for phase in samples["plain"][0]:
        plain, sandbox = (statistics.median(r[phase] for r in samples[m])
                          for m in ("plain", "runsc"))
        print(f"{phase:40} {plain:10.1f} {sandbox:11.1f} {sandbox-plain:11.1f}")
