#!/usr/bin/env python3

import argparse
import subprocess
from subprocess import PIPE
import shutil
from collections import Counter
from pathlib import Path


def log(msg, verbose=True):
    if verbose:
        print(msg)


def run(*args, **kwargs):
    return subprocess.run(list(args), check=True, **kwargs)


def progress(iterable, display=True):
    if display:
        print()
    for i, it in enumerate(iterable):
        if display:
            print(f"\rProgress: {i}", end="", flush=True)
        yield it
    if display:
        print()


def extract_template(line):
    # Example line:
    #  Function void raft::random::detail::rmat_gen_kernel<long, double>(T1 *, T1 *, T1 *, const T2 *, T1, T1, T1, T1, raft::random::RngState):
    line = line.replace("Function", "").replace("void", "").strip()
    if "<" in line:
        line = line.split("<")[0]
    # Example return: raft::random::detail::rmat_gen_kernel
    return line


def get_kernels(cuobjdump, cu_filt, grep, object_file_path):
    try:
        # Executes:
        # > cuobjdump -res-usage file | cu++filt | grep Function
        step1 = run(cuobjdump, "-res-usage", object_file_path, stdout=PIPE)
        step2 = run(cu_filt, input=step1.stdout, stdout=PIPE)
        step3 = run(grep, "Function", input=step2.stdout, stdout=PIPE)

        out_str = step3.stdout.decode(encoding="utf-8", errors="strict")

        return [extract_template(line) for line in out_str.splitlines()]
    except Exception as e:
        print(e)
        return []

def get_object_files(ninja, build_dir, target):
    # Executes:
    # > ninja -C build/dir -t input <target>
    build_dir = Path(build_dir)
    out = run(ninja, "-C", build_dir, "-t", "inputs", target, stdout=PIPE)
    out_str = out.stdout.decode(encoding="utf-8", errors="strict")

    target_path = build_dir / target

    # If the target exists and is an object file, add it to the list of
    # candidates.
    if target_path.exists() and str(target_path).endswith(".o"):
        additional_objects = [target_path]
    else:
        additional_objects = []

    return [
        str(build_dir / line.strip())
        for line in out_str.splitlines()
        if line.endswith(".o")
    ] + additional_objects


def main(
    build_dir,
    target,
    top_n,
    skip_details=False,
    skip_kernels=False,
    skip_objects=False,
    display_progress=True,
    verbose=True,
):
    # Check that we have the right binaries in the environment.
    binary_names = ["ninja", "grep", "cuobjdump", "cu++filt"]
    binaries = list(map(shutil.which, binary_names))
    ninja, grep, cuobjdump, cu_filt = binaries

    fail_on_bins = any(b is None for b in binaries)
    if fail_on_bins:
        for path, name in zip(binaries, binary_names):
            if path is None:
                print(f"Could not find {name}. Make sure {name} is in PATH.")
        exit(1)

    for path, name in zip(binaries, binary_names):
        log(f"Found {name}: {path}", verbose=verbose)

    # Get object files from target:
    object_files = get_object_files(ninja, build_dir, target)

    # Compute the counts of each object-kernel combination
    get_kernel_bins = (cuobjdump, cu_filt, grep)
    obj_kernel_tuples = (
        (obj, kernel)
        for obj in object_files
        for kernel in get_kernels(*get_kernel_bins, obj)
    )
    obj_kernel_counts = Counter(
        tup for tup in progress(obj_kernel_tuples, display=display_progress)
    )

    # Create an index with the kernel counts per object and the object count per kernel:
    obj2kernel = dict()
    kernel2obj = dict()
    kernel_counts = Counter()
    obj_counts = Counter()

    for (obj, kernel), count in obj_kernel_counts.items():
        # Update the obj2kernel and kernel2obj index:
        obj2kernel_ctr = obj2kernel.setdefault(obj, Counter())
        kernel2obj_ctr = kernel2obj.setdefault(kernel, Counter())
        obj2kernel_ctr += Counter({kernel: count})
        kernel2obj_ctr += Counter({obj: count})

        # Update counters:
        kernel_counts += Counter({kernel: count})
        obj_counts += Counter({obj: count})

    # Print summary statistics
    if not skip_objects:
        print("\nObjects with most kernels")
        print("=========================\n")
        for obj, total_count in obj_counts.most_common()[:top_n]:
            print(
                f"{total_count:4d} kernel instances in {obj} ({len(obj2kernel[obj])} kernel templates)"
            )

    if not skip_kernels:
        print("\nKernels with most instances")
        print("===========================\n")
        for kernel, total_count in kernel_counts.most_common()[:top_n]:
            print(
                f"{total_count:4d} instances of {kernel} in {len(kernel2obj[kernel])} objects."
            )

    if skip_details:
        return

    if not skip_objects:
        print("\nDetails: Objects")
        print("================\n")
        for obj, total_count in obj_counts.most_common()[:top_n]:
            print(
                f"{total_count:4d} kernel instances in {obj} across {len(obj2kernel[obj])} templates:"
            )
            for kernel, c in obj2kernel[obj].most_common():
                print(f"    {c:4d}: {kernel}")
            print()

    if not skip_kernels:
        print("\nDetails: Kernels")
        print("================\n")
        for kernel, total_count in kernel_counts.most_common()[:top_n]:
            print(
                f"{total_count:4d} instances of {kernel} in {len(kernel2obj[kernel])} objects:"
            )
            for obj, c in kernel2obj[kernel].most_common():
                print(f"    {c:4d}: {obj}")
            print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=str, help="The ninja target to investigate")
    parser.add_argument(
        "--build-dir",
        type=str,
        default="./",
        help="Build directory",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Log only top N most common objects/kernels",
    )

    parser.add_argument(
        "--skip-details",
        action="store_true",
        help="Show a summary of statistics, but no details.",
    )
    parser.set_defaults(skip_details=False)

    parser.add_argument(
        "--no-progress", action="store_true", help="Do not show progress indication"
    )
    parser.set_defaults(no_progress=False)

    parser.add_argument(
        "--skip-objects", action="store_true", help="Do not show statistics on objects"
    )
    parser.set_defaults(skip_objects=False)

    parser.add_argument(
        "--skip-kernels", action="store_true", help="Do not show statistics on kernels"
    )
    parser.set_defaults(skip_kernels=False)

    parser.add_argument("--verbose", action="store_true")
    parser.set_defaults(verbose=False)

    args = parser.parse_args()

    main(
        args.build_dir,
        args.target,
        args.top_n,
        skip_details=args.skip_details,
        skip_kernels=args.skip_kernels,
        skip_objects=args.skip_objects,
        display_progress=not args.no_progress,
        verbose=args.verbose,
    )
