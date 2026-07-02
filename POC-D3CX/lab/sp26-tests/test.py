import atexit
import shlex
import signal
import sys

import os
os.environ.pop('HIDDEN_TESTS_TOKEN', None)

import json
import argparse
import subprocess
import datetime
import shutil
import tempfile
import time
import re
from enum import Enum, auto
from dataclasses import dataclass, field
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial, update_wrapper
from typing import Any, Callable, TypeVar
from difflib import unified_diff

import toml
from rich import print
from rich.table import Table
from rich.progress import track
from rich.panel import Panel
from rich.syntax import Syntax
from rich.console import Group, RenderableType

from rich.traceback import install
install()

### Settings ###


@dataclass
class EnvironmentConfig:
    test_dir: str = os.path.dirname(__file__)
    temp_dir: str = tempfile.mkdtemp()
    output_dir: str = temp_dir
    random_filename: bool = True
    phase: str = "local"
    sandbox: bool = False
    
    zero_ir_path: str = os.path.join(test_dir, "ir", "zero.py")
    accipit_ir_path: str = os.path.join(test_dir, "ir", "accipit.py")
    venus_jar: str = os.path.join(test_dir, "venus.jar")
    coverage_py: str = os.path.join(test_dir, "coverage.py")
    io_c: str = os.path.join(test_dir, "libs", "io.c")
    timer_c_path: str = os.path.join(test_dir, "libs", "timer.c")
    
    python: str = sys.executable
    java: str | None = shutil.which("java")
    cc: str | None = shutil.which("gcc") or shutil.which("clang")
    rv32_gcc: str | None = shutil.which("riscv32-unknown-elf-gcc")
    rv32_qemu: str | None = shutil.which("qemu-riscv32")
    bwrap: str | None = shutil.which("bwrap")

    def __post_init__(self):
        atexit.register(shutil.rmtree, self.temp_dir)

envs = EnvironmentConfig()

test_score = 0

@dataclass
class TestConfig:
    verbose: bool = False
    use_qemu: bool = False
    use_accipit: bool = False
    parallel: bool = True
    check_ssa: bool = False
    precise_timing: bool = True
    timeout: float = 10.0
    extra_cflags: list[str] = field(default_factory=lambda: [envs.io_c])
    
cfg = TestConfig()

### Color Utils ###


def red(s: str) -> str:
    return f"[bold red]{s}[/bold red]"

def green(s: str) -> str:
    return f"[bold green]{s}[/bold green]"

def blue(s: str) -> str:
    return f"[bold blue]{s}[/bold blue]"

def yellow(s: str) -> str:
    return f"[bold yellow]{s}[/bold yellow]"

def box(s: str) -> str:
    return f"[bold reverse white on black]{s}[/bold reverse white on black]"

### Test Utils ###


@dataclass
class Test:
    filename: str
    inputs: list[str] | None
    expected: list[str] | None
    should_return: int | None

    @staticmethod
    def parse_file(filename: str) -> "Test":
        content = open(filename).readlines()
        comments: list[str] = []
        for line in content:
            # get comment, start with //
            if line.strip().startswith("//"):
                comments.append(line.strip()[2:].strip())
            else:
                break
        if len(comments) >= 2 and comments[0].startswith("Input:") and comments[1].startswith("Output:"):   # input and output
            input = comments[0].replace("Input:", "").split()
            if input[0] == "None":
                input = []
            expected = comments[1].replace("Output:", "").split()
            if expected[0] == "None":
                expected = []
            return Test(filename, input, expected, None)
        elif len(comments) >= 1 and comments[0].startswith("Return"):
            # Return 1 - Syntax Error: rvalue cannot be assigned to
            match = re.search(r"Return (\d+)", comments[0])
            return Test(filename, None, None, int(match.group(1)) if match else None)
        else:   # should success
            return Test(filename, None, None, 0)

    def __str__(self):
        return f"Test({self.filename}, {self.inputs}, {self.expected}, {self.should_return})"

def count_effective_lines(filename: str) -> int:
    """Count non-blank, non-comment lines in a C/SysY source file.
    Removes both // line comments and /* */ block comments before counting."""
    content = open(filename).read()
    content = re.sub(r'/\*[\s\S]*?\*/|//.*', '', content)
    return sum(1 for line in content.splitlines() if line.strip())

class ResultType(Enum):
    ACCEPTED = auto()
    WRONG_ANSWER = auto()
    RUN_TIMEOUT = auto()
    COMPILE_TIMEOUT = auto()
    COMPILE_ERROR = auto()
    RUNTIME_ERROR = auto()
    
class TimeType(Enum):
    CYCLES = auto()
    STEPS = auto()
    NANOSECONDS = auto()

class TestResult:
    def __init__(self,
                 test: Test,
                 output: str | None | list[str] = None,
                 result_type: ResultType | None = None,
                 run_time: float | None = None,
                 run_time_type: TimeType = TimeType.STEPS,
                 error: Exception | None = None,
                 return_code: int = 0,
    ) -> None:
        self.test = test
        self.output = output
        self.run_time = run_time
        self.run_time_type = run_time_type
        self.error = error
        self.return_code = return_code
        if test.should_return is not None:
            self.result = ResultType.ACCEPTED if return_code == test.should_return else ResultType.WRONG_ANSWER
        else:
            if result_type is not None and result_type != ResultType.ACCEPTED:
                self.result = result_type
            else:
                if test.expected is None:
                    self.result = ResultType.WRONG_ANSWER if output else ResultType.ACCEPTED
                else:
                    self.result = ResultType.ACCEPTED if output == test.expected else ResultType.WRONG_ANSWER

_T = TypeVar("_T")
def execute_with_timing(func: Callable[..., _T], *args: Any, repeat: int = 10, use_last: int = 5, **kwargs: Any) -> tuple[list[_T], list[float]]:
    """
    Run a function multiple times and return the results and times.

    Args:
        func (Callable): The function to measure (no parameters).
        repeat (int): Total number of repetitions, default is 10.
        use_last (int): Number of last results to return, default is 5.

    Returns:
        Tuple[List[Any], List[float]]: List of results and list of times.
    """
    results: list[_T] = []
    times: list[float] = []

    for _ in range(repeat):
        start_time = time.perf_counter()  # Higher precision timer
        result = func(*args, **kwargs)  # Execute the function
        end_time = time.perf_counter()

        results.append(result)  # Store the result
        times.append(end_time - start_time)  # Store the time

    return results[-use_last:], times[-use_last:]

def run_commands(commands: list[list[str]], *args: Any, **kwargs: Any) -> None:
    for command in commands:
        subprocess.run(command, capture_output=True, check=True, timeout=cfg.timeout, *args, **kwargs)

def wrap_compiler_command(
    compiler_cmd: list[str],
    source_root: str,
    input_files: list[str] | None = None,
    output_files: list[str] | None = None,
) -> tuple[list[str], list[tuple[Path, Path]], Path | None]:
    if not envs.sandbox:
        return compiler_cmd, [], None

    assert envs.bwrap is not None, "Compiler sandbox is enabled, but bubblewrap (bwrap) is not available."
    source_root_path = Path(source_root).resolve(strict=False)
    compiler_path = Path(compiler_cmd[0]).resolve(strict=False)
    cwd_path = Path.cwd().resolve()
    input_files = input_files or []
    output_files = output_files or []

    path_map: dict[str, str] = {}
    bwrap_cmd = [
        envs.bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--dir", "/inputs",
        "--setenv", "HOME", "/tmp",
        "--setenv", "TMPDIR", "/tmp",
    ]

    for system_dir in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/lib32", "/etc", "/opt"):
        if os.path.exists(system_dir):
            bwrap_cmd += ["--ro-bind", system_dir, system_dir]

    bwrap_cmd += ["--ro-bind", str(source_root_path), "/workspace"]

    if cwd_path.is_relative_to(source_root_path):
        sandbox_cwd = str(Path("/workspace") / cwd_path.relative_to(source_root_path))
    else:
        bwrap_cmd += ["--ro-bind", str(cwd_path), "/work"]
        sandbox_cwd = "/work"

    if compiler_path.is_relative_to(source_root_path):
        sandbox_compiler = str(Path("/workspace") / compiler_path.relative_to(source_root_path))
    else:
        bwrap_cmd += ["--ro-bind", str(compiler_path), "/compiler"]
        sandbox_compiler = "/compiler"

    for index, input_file in enumerate(input_files):
        host_input = Path(input_file).resolve(strict=False)
        sandbox_input = f"/inputs/input{index}{host_input.suffix}"
        bwrap_cmd += ["--ro-bind", str(host_input), sandbox_input]
        path_map[str(host_input)] = sandbox_input

    output_copy_plan: list[tuple[Path, Path]] = []
    scratch_output_dir: Path | None = None
    for index, output_file in enumerate(output_files):
        if scratch_output_dir is None:
            scratch_output_dir = Path(tempfile.mkdtemp(dir=envs.temp_dir, prefix="sandbox-out-"))
            bwrap_cmd += ["--bind", str(scratch_output_dir), "/outputs"]
        host_output = Path(output_file).resolve(strict=False)
        scratch_output = scratch_output_dir / f"output{index}{host_output.suffix}"
        path_map[str(host_output)] = str(Path("/outputs") / scratch_output.name)
        output_copy_plan.append((scratch_output, host_output))

    sandbox_args: list[str] = []
    for arg in compiler_cmd[1:]:
        resolved_arg = str(Path(arg).resolve(strict=False))
        sandbox_args.append(path_map.get(resolved_arg, arg))

    return bwrap_cmd + ["--chdir", sandbox_cwd, sandbox_compiler, *sandbox_args], output_copy_plan, scratch_output_dir

def check_bwrap() -> None:
    assert envs.bwrap is not None, "Compiler sandbox is enabled, but bubblewrap (bwrap) is not available."
    command = [
        envs.bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
    ]
    for system_dir in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/lib32", "/etc", "/opt"):
        if os.path.exists(system_dir):
            command += ["--ro-bind", system_dir, system_dir]
    command += ["/bin/sh", "-lc", "true"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, (
        "Compiler sandbox cannot start bubblewrap in the current container. "
        f"{result.stderr.strip()}"
    )

def run_compiler_command(
    compiler_cmd: list[str],
    *args: Any,
    source_root: str,
    input_files: list[str] | None = None,
    output_files: list[str] | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    wrapped_cmd, output_copy_plan, scratch_output_dir = wrap_compiler_command(
        compiler_cmd,
        source_root=source_root,
        input_files=input_files,
        output_files=output_files,
    )
    try:
        result = subprocess.run(wrapped_cmd, *args, **kwargs)
        for scratch_output, host_output in output_copy_plan:
            if scratch_output.exists():
                host_output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(scratch_output, host_output)
        return result
    except subprocess.TimeoutExpired as e:
        e.cmd = compiler_cmd
        raise
    except subprocess.CalledProcessError as e:
        e.cmd = compiler_cmd
        raise
    finally:
        if scratch_output_dir is not None:
            shutil.rmtree(scratch_output_dir, ignore_errors=True)

def generate_temp_input_file(filename: str) -> str:
    """Generate a temp file from the given file path."""
    if not envs.random_filename:
        return filename
    input_file_path = tempfile.NamedTemporaryFile(dir=envs.output_dir, suffix=".sy", delete=False)
    shutil.copy(filename, input_file_path.name)
    return input_file_path.name

def test_exception_handling(func: Callable[..., TestResult]) -> Callable[..., TestResult]:
    def wrapper(compiler: str, test: Test, *args: Any, **kwargs: Any) -> TestResult:
        try:
            return func(compiler, test, *args, **kwargs)
        # except AssertionError:
        #     raise
        except subprocess.TimeoutExpired as e:
            if e.cmd[0] == compiler:
                return TestResult(test, result_type=ResultType.COMPILE_TIMEOUT, error=e)
            else:
                return TestResult(test, result_type=ResultType.RUN_TIMEOUT, error=e)
        except subprocess.CalledProcessError as e:
            if e.cmd[0] == compiler:
                return TestResult(test, result_type=ResultType.COMPILE_ERROR, error=e, return_code=e.returncode)
            else:
                return TestResult(test, result_type=ResultType.RUNTIME_ERROR, error=e, return_code=e.returncode)
        # except Exception as e:
        #     return TestResult(test, result_type=ResultType.RUNTIME_ERROR, error=e)
    return update_wrapper(wrapper, func)

@test_exception_handling
def compile_run_result(compiler: str, test: Test, src_file_path: str, use_qemu: bool) -> TestResult:
    executable_file_path = os.path.join(
        envs.output_dir,
        Path(src_file_path).with_suffix(
            ".exe" if sys.platform.startswith("win") else ""
        ).name
    )
    if cfg.precise_timing:
        run_commands([
            [compiler, src_file_path, envs.timer_c_path, "-o", executable_file_path, "-Wno-implicit-function-declaration"] + \
                (["-DRV32ASM"] if use_qemu else []) + cfg.extra_cflags,
        ])
    else:
        run_commands([
            [compiler, src_file_path, "-o", executable_file_path] + cfg.extra_cflags,
        ])

    if use_qemu:
        assert envs.rv32_qemu is not None, "qemu-riscv32 not found."
        cmd = [envs.rv32_qemu, executable_file_path]
    else:
        cmd = [executable_file_path]
 
    results, run_times = execute_with_timing(
        subprocess.run,
        cmd,
        input="\n".join(test.inputs) if test.inputs is not None else None,
        capture_output=True,
        text=True,
        timeout=cfg.timeout,
        check=True,
    )
    sample_result = results[-1]
    sample_output = sample_result.stdout.strip().split("\n")
    # case 1: Execution time: %llu cycles
    match = re.search(r"Execution time: (\d+) cycles", sample_output[-1])
    if match:
        cycles: list[int] = []
        for result in results:
            output = result.stdout.strip().split("\n")
            time_line = output[-1]
            match = re.search(r"Execution time: (\d+) cycles", time_line)
            assert match, "Execution time not found."
            cycles.append(int(match.group(1)))
        return TestResult(test, sample_output[:-1], run_time=sum(cycles) / len(cycles), run_time_type=TimeType.CYCLES)
    # case 2: Execution time: %ld s %ld ns
    match = re.search(r"Execution time: (\d+) s (\d+) ns", sample_output[-1])
    if match:
        times: list[int] = []
        for result in results:
            output = result.stdout.strip().split("\n")
            time_line = output[-1]
            match = re.search(r"Execution time: (\d+) s (\d+) ns", time_line)
            assert match, "Execution time not found."
            times.append(int(int(match.group(1)) * 1e9 + int(match.group(2))))
        return TestResult(test, sample_output[:-1], run_time=sum(times) / len(times), run_time_type=TimeType.NANOSECONDS)
    # case 3: no match, use run_times avg
    return TestResult(test, sample_output, run_time=int(sum(run_times) / len(run_times) * 1e9), run_time_type=TimeType.NANOSECONDS)

@test_exception_handling
def run_with_src(compiler: str, test: Test, qemu: bool = False) -> TestResult:  # lab0
    assert test.expected is not None, f"{test.filename} has no expected output."
    src_file_path = os.path.join(envs.output_dir, Path(test.filename).with_suffix(".c").name)
    shutil.copy(test.filename, src_file_path)
    
    return compile_run_result(compiler, test, src_file_path, qemu)

@test_exception_handling
def run_only_compiler(compiler: str, test: Test) -> TestResult:  # lab1, lab2
    assert test.inputs is None, "Not implemented input for lab1 or lab2"
    src_file_path = generate_temp_input_file(test.filename)
    run_compiler_command(
        [compiler, src_file_path],
        capture_output=True,
        timeout=cfg.timeout,
        check=True,
        source_root=str(Path(compiler).resolve().parent),
        input_files=[src_file_path],
    )
    return TestResult(test, result_type=ResultType.ACCEPTED)

@test_exception_handling
def run_with_ir(compiler: str, test: Test, accipit: bool) -> TestResult:  # lab3
    src_file_path = generate_temp_input_file(test.filename)
    ir_file_path = os.path.join(
        envs.output_dir,
        Path(src_file_path).with_suffix(
            ".acc" if accipit else ".zir"
        ).name
    )
    ir_path = envs.accipit_ir_path if accipit else envs.zero_ir_path
    assert os.path.exists(ir_path), f"{ir_path} not found."
    assert test.expected is not None, f"{test.filename} has no expected output."
    result = run_compiler_command(
        [compiler, src_file_path, ir_file_path, '--ir'],
        capture_output=True,
        check=True,
        timeout=cfg.timeout,
        source_root=str(Path(compiler).resolve().parent),
        input_files=[src_file_path],
        output_files=[ir_file_path],
    )
    
    result = subprocess.run(
        [envs.python, ir_path, ir_file_path] + (["--ssa"] if cfg.check_ssa and not accipit else []),
        input="\n".join(test.inputs) if test.inputs is not None else None,
        capture_output=True,
        text=True,
        timeout=cfg.timeout,
        check=True
    )
    output = result.stdout.split("\n")
    output = [line.strip() for line in output if line.strip() != ""]
    if output:
        # extract run step in the last line "Exit with code {exit_code} within {run_step} steps."
        match = re.search(r"within (\d+) steps", output[-1])
        if match:
            run_step = int(match.group(1))
        else:
            run_step = None
        output = output[:-1]
    else:
        run_step = None
    return TestResult(test, output, run_time=run_step, run_time_type=TimeType.STEPS)

@test_exception_handling
def run_with_asm(compiler: str, test: Test, qemu: bool = False) -> TestResult:  # lab4
    assert test.expected is not None, f"{test.filename} has no expected output."

    src_file_path = generate_temp_input_file(test.filename)
    # compile to assembly
    assembly_file_path = os.path.join(envs.output_dir, Path(src_file_path).with_suffix(".S").name)
    run_compiler_command(
        [compiler, src_file_path, assembly_file_path] + (['--venus'] if not qemu else []),  # add --venus flag
        capture_output=True,
        timeout=cfg.timeout,
        check=True,
        source_root=str(Path(compiler).resolve().parent),
        input_files=[src_file_path],
        output_files=[assembly_file_path],
    )
    
    if qemu:
        assert envs.rv32_gcc is not None, "riscv32-unknown-elf-gcc not found."
        assert envs.rv32_qemu is not None, "qemu-riscv32 not found."

        return compile_run_result(envs.rv32_gcc, test, assembly_file_path, use_qemu=True)    
    else:   # run with venus
        assert envs.java is not None, "java not found."
        assert os.path.exists(envs.venus_jar), f"{envs.venus_jar} not found."

        result = subprocess.run(
            [envs.java, "-jar", envs.venus_jar, assembly_file_path, '-ahs', '-ms', '-1'],         # -ms -1: ignore max step limit
            input="\n".join(test.inputs) if test.inputs is not None else None,
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
            check=True
        )
        output = result.stdout.strip().split("\n")
        # if the last line is "Exited with error code {exit_code}", remove it
        if len(output) > 1 and output[-1].startswith("E"):
            output = output[:-1]
        output = [line.strip() for line in output if line.strip() != ""]
        result_step = subprocess.run(
            [envs.java, "-jar", envs.venus_jar, assembly_file_path, '-ahs', '-n', '-ms', '-1'],   # -n: only output step count
            input="\n".join(test.inputs) if test.inputs is not None else None,
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
            check=True
        )
        run_step = int(result_step.stdout.strip())
        return TestResult(test, output, run_time=run_step, run_time_type=TimeType.STEPS)

### Phase Result Utils ###


def save_phase_result(lab: str, phase: str, passed: int, total: int, output_dir: str, score: float | None = None) -> None:
    data: dict = {"passed": passed, "total": total}
    if score is not None:
        data["score"] = score
    path = os.path.join(output_dir, f"{lab}_{phase}.json")
    with open(path, "w") as f:
        json.dump(data, f)

def load_phase_result(lab: str, phase: str, output_dir: str) -> dict | None:
    path = os.path.join(output_dir, f"{lab}_{phase}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def summary(test_results: list[TestResult], source_folder: str, verbose: bool = False):
    assert len(test_results) > 0, "no tests found."

    def path_to_print(path_str: str) -> str:
        path: Path = Path(path_str)
        if path.is_relative_to(envs.test_dir):
            return path.relative_to(envs.test_dir).as_posix()
        elif path.is_relative_to(Path(source_folder)):
            return path.relative_to(Path(source_folder)).as_posix()
        else:
            return path.as_posix()
    
    def colored_result(result: ResultType) -> str:
        color_map = {
            ResultType.ACCEPTED: green,
            ResultType.WRONG_ANSWER: red,
            ResultType.RUN_TIMEOUT: blue,
            ResultType.COMPILE_TIMEOUT: blue,
            ResultType.COMPILE_ERROR: yellow,
            ResultType.RUNTIME_ERROR: yellow
        }
        return color_map[result](result.name.replace("_", " ").title())
    
    def format_time(run_time: float, run_time_type: TimeType) -> str:
        if run_time_type == TimeType.CYCLES:
            return f"{run_time:.2f} cycles"
        elif run_time_type == TimeType.STEPS:
            return f"{run_time} steps"
        elif run_time_type == TimeType.NANOSECONDS:
            if run_time < 1e3:
                return f"{run_time:.2f} ns"
            elif run_time < 1e6:
                return f"{run_time/1e3:.2f} us"
            elif run_time < 1e9:
                return f"{run_time/1e6:.2f} ms"
            else:
                return f"{run_time/1e9:.2f} s"
        else:
            raise ValueError("Invalid TimeType.")
        
    def truncate_lines(s: str, show_lines: int = 10) -> str:
        lines = s.split("\n")
        if len(lines) <= show_lines * 3:
            return s
        omitted = len(lines) - show_lines * 2
        return "\n".join(
            lines[:show_lines] + \
            [f"[dim]... {omitted} lines omitted ...[/dim]"] + \
            lines[-show_lines:]
        )
        
    def compiler_return_code_to_text(return_code: int) -> str:
        return {
            0: "CompilerSuccess",
            1: "SyntaxError",
            2: "NotAssignable",
            3: "ExcessInitializers",
            4: "IncompatibleConversion",
            5: "InvalidOperands",
            6: "NotSubscriptable",
            7: "ReturnMismatch",
            8: "NotIntegerSubscript",
            9: "NotCallable",
            10: "Undeclared",
            11: "Redefinition",
            12: "InvalidInitializer",
            13: "ArgNumMismatch",
        }.get(return_code, "UnknownError")

    if verbose:
        for test_result in test_results:
            # Create a panel for each test
            test_filename = path_to_print(test_result.test.filename)
            result_text = colored_result(test_result.result)

            title = f"[bold]{test_filename}[/bold] {result_text}"
            # WRONG_ANSWER case
            if test_result.result == ResultType.WRONG_ANSWER:
                body = []

                if test_result.test.should_return is not None:
                    table = Table(show_header=False, box=None, highlight=True)
                    table.add_column(style="yellow italic", justify="right")
                    table.add_column()
                    if isinstance(test_result.error, subprocess.CalledProcessError):
                        try:
                            stdout = test_result.error.stdout.decode().strip() or "[dim]No stdout[/dim]"
                        except:
                            stdout = test_result.error.stdout or "[dim]No stdout[/dim]"
                        try:
                            stderr = test_result.error.stderr.decode().strip() or "[dim]No stderr[/dim]"
                        except:
                            stderr = test_result.error.stderr or "[dim]No stderr[/dim]"
                            
                        returncode = test_result.error.returncode
                        if returncode and returncode < 0:
                            try:
                                return_text = f"{str(signal.Signals(-returncode))} ({returncode})"
                            except ValueError:
                                return_text = f"{returncode}"
                        else:
                            return_text = f"{returncode}"

                        # Add stdout/stderr in a table
                        table.add_row("command", str(test_result.error.cmd))
                        table.add_row("expected return code", str(test_result.test.should_return) + f" ({compiler_return_code_to_text(test_result.test.should_return)})")
                        table.add_row("got return code", str(test_result.return_code) + f" ({compiler_return_code_to_text(test_result.return_code)})")
                        table.add_row("stdout", truncate_lines(stdout))
                        table.add_row("stderr", truncate_lines(stderr))
                    else:
                        table.add_row("expected return code", str(test_result.test.should_return) + f" ({compiler_return_code_to_text(test_result.test.should_return)})")
                        table.add_row("got return code", str(test_result.return_code) + f" ({compiler_return_code_to_text(test_result.return_code)})")
                    print()
                    print(Panel(table, title=title, title_align='left', expand=True, highlight=True))
                else:
                    expected = test_result.test.expected or []
                    got = test_result.output or []

                    # Generate diff
                    diff = unified_diff(
                        expected,
                        got,
                        fromfile="Expected",
                        tofile="Got",
                        lineterm=""
                    )

                    # Highlight diff using Syntax
                    diff_text = "\n".join(diff)
                    if diff_text.strip():
                        diff_syntax = Syntax(truncate_lines(diff_text), "diff", line_numbers=False)
                    else:
                        diff_syntax = "[dim]No differences found[/dim]"

                    body.append(diff_syntax)
                    print()
                    print(Panel(Group(*body), title=title, title_align='left', expand=True, highlight=True))

            # Other non-ACCEPTED errors
            elif test_result.result != ResultType.ACCEPTED:
                body: list[RenderableType] = []

                if isinstance(test_result.error, subprocess.CalledProcessError):
                    try:
                        stdout = test_result.error.stdout.decode().strip() or "[dim]No stdout[/dim]"
                    except:
                        stdout = test_result.error.stdout or "[dim]No stdout[/dim]"
                    try:
                        stderr = test_result.error.stderr.decode().strip() or "[dim]No stderr[/dim]"
                    except:
                        stderr = test_result.error.stderr or "[dim]No stderr[/dim]"
                        
                    returncode = test_result.error.returncode
                    if returncode and returncode < 0:
                        try:
                            return_text = f"{str(signal.Signals(-returncode))} ({returncode})"
                        except ValueError:
                            return_text = f"{returncode}"
                    else:
                        return_text = f"{returncode}"

                    # Add stdout/stderr in a table
                    table = Table(show_header=False, box=None, highlight=True)
                    table.add_column(style="yellow italic", justify="right")
                    table.add_column()
                    table.add_row("command", str(test_result.error.cmd))
                    table.add_row("exit code", return_text)
                    table.add_row("stdout", truncate_lines(stdout))
                    table.add_row("stderr", truncate_lines(stderr))
                    print()
                    print(Panel(table, title=title, title_align='left', expand=True, highlight=True))
                elif isinstance(test_result.error, subprocess.TimeoutExpired):
                    try:
                        assert test_result.error.stdout is not None
                        stdout = test_result.error.stdout.decode().strip() or "[dim]No stdout[/dim]"
                    except:
                        stdout = "[dim]No stdout[/dim]"
                    try:
                        assert test_result.error.stderr is not None
                        stderr = test_result.error.stderr.decode().strip() or "[dim]No stderr[/dim]"
                    except:
                        stderr = "[dim]No stderr[/dim]"
                    table = Table(show_header=False, box=None, highlight=True)
                    table.add_column(style="yellow italic", justify="right")
                    table.add_column()
                    table.add_row("command", str(test_result.error.cmd))
                    table.add_row("Timeout", f"{test_result.error.timeout} seconds")
                    table.add_row("stdout", truncate_lines(stdout))
                    table.add_row("stderr", truncate_lines(stderr))
                    print()
                    print(Panel(table, title=title, title_align='left', expand=True, highlight=True))
                else:
                    body.append("[bold]Error Details:[/bold]")
                    body.append(f"{test_result.error}")
                    print()
                    print(Panel(Group(*body), title=title, title_align='left', expand=True, highlight=True))

    # Create a Rich Table
    table = Table(title="Test Results", box=None, expand=True, highlight=True)
    table.add_column("Test File", style="bold", justify="left")
    table.add_column("Result", justify="left")
    table.add_column("Time", justify="left")

    for i, test_result in enumerate(test_results):
        test_file = path_to_print(test_result.test.filename)
        result = colored_result(test_result.result)
        if test_result.run_time is not None:
            table.add_row(test_file, result, format_time(test_result.run_time, test_result.run_time_type))
        else:
            table.add_row(test_file, result)

    print()
    print(table)
    print()

def init_worker(envs: EnvironmentConfig, cfg: TestConfig) -> None:
    globals()['envs'] = envs
    globals()['cfg'] = cfg

def test_lab(source_folder: str, lab: str, files: list[str],
             hidden_dir: str | None = None) -> None:
    # Determine which tests to load based on phase
    if envs.phase == "hidden":
        # Load tests from the hidden directory (only lab2/lab3/lab4 reach here)
        assert hidden_dir is not None, "--hidden-dir required for --phase hidden"
        hidden_lab_dir = Path(hidden_dir) / lab
        if not hidden_lab_dir.exists():
            print(yellow(f"Hidden test directory {hidden_lab_dir} not found, skipping."))
            save_phase_result(lab, "hidden", 0, 0, envs.output_dir)
            return
        tests_paths = sorted(hidden_lab_dir.glob("*.sy"))
        if not tests_paths:
            print(yellow(f"No hidden tests found in {hidden_lab_dir}, skipping."))
            save_phase_result(lab, "hidden", 0, 0, envs.output_dir)
            return
        print(box(f"Running {lab} hidden test..."))
    else:
        # Normal / public phase: original test discovery logic
        print(box(f"Running {lab} {'public ' if envs.phase == 'public' else ''}test..."))
        if files:
            tests_paths = [path for file in files for path in (Path(file).rglob("*.sy") if os.path.isdir(file) else [Path(file)])]
        else:
            if lab == 'lab0':
                tests_paths = list((Path(source_folder) / "appends" / "lab0").glob("*.sy"))
            elif 'bonus' in lab:
                tests_paths = list((Path(envs.test_dir) / "tests" / "lab4").glob("*.sy"))
                if lab == 'bonus2':
                    tests_paths += list((Path(source_folder) / "appends" / "bonus2").glob("*.sy"))
                elif lab == 'bonus3':
                    tests_paths += list((Path(envs.test_dir) / "tests" / "bonus3").glob("*.sy"))
                    tests_paths += list((Path(source_folder) / "appends" / "bonus3").glob("*.sy"))
            else:
                tests_paths = list((Path(envs.test_dir) / "tests" / lab).glob("*.sy"))
        tests_paths = sorted(tests_paths)

    if lab == 'lab0':
        compiler = envs.cc if not cfg.use_qemu else envs.rv32_gcc
        assert compiler is not None, "gcc or clang not found." if not cfg.use_qemu else "riscv32-unknown-elf-gcc not found."
    else:
        compiler = shutil.which("compiler", path=source_folder)
        assert compiler is not None, "compiler not found in the source folder."

    test_func: dict[str, Callable[[str, Test], TestResult]] = {
        'lab0': partial(run_with_src, qemu=cfg.use_qemu),
        'lab1': run_only_compiler,
        'lab2': run_only_compiler,
        'lab3': partial(run_with_ir, accipit=cfg.use_accipit),
        'lab4': partial(run_with_asm, qemu=cfg.use_qemu),
        'bonus1': partial(run_with_asm, qemu=cfg.use_qemu),
        'bonus2': partial(run_with_asm, qemu=cfg.use_qemu),
        'bonus3': partial(run_with_asm, qemu=True),
    }

    tests = [Test.parse_file(str(t)) for t in tests_paths]

    if cfg.parallel:
        results: dict[int, TestResult] = {}
        with ProcessPoolExecutor(initializer=init_worker, initargs=(envs, cfg)) as executor:
            future_to_index = {executor.submit(test_func[lab], compiler, test): i for i, test in enumerate(tests)}
            for future in track(as_completed(future_to_index), total=len(tests), description="Running tests", disable=not cfg.verbose):
                index = future_to_index[future]
                result = future.result()
                results[index] = result
        test_results = [results[i] for i in range(len(tests))]
    else:
        test_results = [test_func[lab](compiler, test) for test in track(tests, description="Running tests", disable=not cfg.verbose)]

    summary(test_results, source_folder,
            verbose=False if envs.phase == "hidden" else cfg.verbose)

    passed = len([r for r in test_results if r.result == ResultType.ACCEPTED])
    total = len(test_results)

    # --- Hidden phase: save result and return, no global score ---
    if envs.phase == "hidden":
        save_phase_result(lab, "hidden", passed, total, envs.output_dir)
        print(f"Hidden: {passed}/{total} tests passed")
        print(f"[bold]Hidden test score: {100.0 * passed / total:.2f}[/bold]")
        print()
        return

    # --- Public phase or local mode ---
    if files:   # do not calculate score if files are provided
        return

    global test_score

    if envs.phase == "public":
        # Save public result; do NOT assert all passed or print Test score
        lab0_score = None
        if lab == 'lab0':
            # Run coverage check in public phase too
            try:
                subprocess.run([envs.python, envs.coverage_py, *map(lambda x: x.filename, tests)], check=True)
                print(green("lab0 coverage test passed."))
            except Exception:
                assert False, "lab0 coverage test failed."
            if total < 5:
                assert False, "lab0 test cases are less than 5."
            coverage_score = 50.0
            # Check if any test file has more than 50 effective lines
            line_score = 0.0
            for t in tests:
                eff = count_effective_lines(t.filename)
                print(f"  {t.filename}: {eff} effective lines")
                if eff > 50:
                    line_score = 50.0
            assert line_score > 0, "lab0 effective line count check failed (no file has >50 effective lines)."
            print(green("lab0 effective line count check passed (>50 lines found)."))
            lab0_score = coverage_score + line_score
        save_phase_result(lab, "public", passed, total, envs.output_dir, score=lab0_score)
        print(f"Public: {passed}/{total} tests passed")
        print(f"[bold]Public test score: {(lab0_score if lab0_score is not None else 100.0 * passed / total):.2f}[/bold]")
        print()
        return

    # --- Local mode: original full behavior ---
    if lab != 'lab0':
        test_score = 100 * passed / total
    assert passed == total, f"{passed}/{total} tests passed."
    print(green("All tests passed!"))
    print()

    if lab == 'lab0':
        # test coverage
        try:
            result = subprocess.run([envs.python, envs.coverage_py, *map(lambda x: x.filename, tests)], check=True)
            print(green(f"lab0 coverage test passed."))
        except Exception:
            assert False, f"lab0 coverage test failed."
        assert total >= 5, "lab0 test cases are less than 5."
        coverage_score = 50
        # Check if any test file has more than 50 effective lines
        line_score = 0
        for t in tests:
            eff = count_effective_lines(t.filename)
            print(f"  {t.filename}: {eff} effective lines")
            if eff > 50:
                line_score = 50
        assert line_score > 0, "lab0 effective line count check failed (no file has >50 effective lines)."
        print(green("lab0 effective line count check passed (>50 lines found)."))
        test_score = coverage_score + line_score


def score_phase(lab: str, source_folder: str, output_dir: str, public_weight: int, hidden_weight: int) -> None:
    """Read saved phase results, compute weighted final score, and print it."""
    global test_score

    pub = load_phase_result(lab, "public", output_dir)
    assert pub is not None, f"Public phase result not found for {lab}. Run --phase public first."

    hid = load_phase_result(lab, "hidden", output_dir)

    # Labs without hidden tests (lab0, lab1, bonus*): ignore hidden weight
    has_hidden = lab in ("lab2", "lab3", "lab4") and hid is not None and hid["total"] > 0

    # Public score
    if lab == "lab0":
        # lab0 stores precomputed score (coverage + case count)
        pub_score = pub.get("score", 0.0)
    else:
        pub_score = 100.0 * pub["passed"] / pub["total"] if pub["total"] > 0 else 0.0

    if has_hidden:
        hid_score = 100.0 * hid["passed"] / hid["total"]
        total_weight = public_weight + hidden_weight
        final_score = pub_score * public_weight / total_weight + hid_score * hidden_weight / total_weight
        print(f"Public:  {pub['passed']}/{pub['total']} passed ({pub_score:.2f})")
        print(f"Hidden:  {hid['passed']}/{hid['total']} passed ({hid_score:.2f})")
    else:
        final_score = pub_score
        print(f"Public:  {pub['passed']}/{pub['total']} passed ({pub_score:.2f})")

    test_score = final_score
    
    if has_hidden:
        assert pub["passed"] == pub["total"] and hid["passed"] == hid["total"], f"Not all tests passed. Public: {pub['passed']}/{pub['total']}, Hidden: {hid['passed']}/{hid['total']}."
    else:
        assert pub["passed"] == pub["total"], f"Not all tests passed. Public: {pub['passed']}/{pub['total']}."

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test your compiler.")
    parser.add_argument("lab", type=str, help="Which lab to test",
                            choices=[
                                "lab0", "lab1", "lab2", "lab3", "lab4",
                                "bonus1", "bonus2", "bonus3"
                            ])
    parser.add_argument("repo_path", type=str, nargs='?', default=os.getcwd(), help="Path to your repository. Defaults to the current working directory.")
    parser.add_argument("-f", "--file", nargs="*", help="Specific test files/dirs to run. Will not record score.")
    parser.add_argument("-o", "--output", type=str, help="Output directory for test results.")
    
    str2bool: Callable[[str], bool] = lambda x: x.lower() in {'true', 't', 'yes', 'y', '1'}
    parser.add_argument("-v", "--verbose", type=str2bool, nargs='?', const=True, help="Print detailed error messages.")
    parser.add_argument("--use-qemu", "--use_qemu", "--qemu", type=str2bool, nargs='?', const=True, help="Use qemu-riscv32 to run tests.")
    parser.add_argument("--use-accipit", "--use_accipit", "--accipit", type=str2bool, nargs='?', const=True, help="Use Accipit IR instead of Zero IR to run tests.")
    parser.add_argument("--parallel", type=str2bool, nargs='?', const=True, help="Run tests in parallel.")
    parser.add_argument("--check-ssa", "--check_ssa", type=str2bool, nargs='?', const=True, help="Check SSA form in lab3. (Zero IR Only)")
    parser.add_argument("--precise-timing", "--precise_timing", type=str2bool, nargs='?', const=True, help="Measure precise timing (build with measure_time.c).")
    parser.add_argument("--timeout", type=float, help="Timeout for each test case.")
    parser.add_argument("--extra-cflags", "--extra_cflags", nargs='*', help="Extra cflags for gcc/clang.")
    parser.add_argument("--sandbox", action="store_true",
                        help="Run the compiler inside the bubblewrap sandbox.")
    
    # Hidden test arguments (CI use only)
    parser.add_argument("--phase", type=str, choices=["local", "public", "hidden", "score"], default="local",
                        help="CI phase: public=run public tests, hidden=run hidden tests, score=compute final weighted score.")
    parser.add_argument("--hidden-dir", "--hidden_dir", type=str, default=None,
                        help="Directory containing hidden test cases (used with --phase hidden).")
    parser.add_argument("--public-weight", "--public_weight", type=int, default=80,
                        help="Weight for public tests in final score (default: 80).")
    parser.add_argument("--hidden-weight", "--hidden_weight", type=int, default=20,
                        help="Weight for hidden tests in final score (default: 20).")

    args = parser.parse_args()
    repo_path, lab, files = args.repo_path, args.lab, args.file
    envs.phase = args.phase
    envs.sandbox = args.sandbox
    
    if args.output:
        envs.output_dir = args.output
        Path(envs.output_dir).mkdir(parents=True, exist_ok=True)
        print(f"All compiled files will be stored in {envs.output_dir}")
    if args.extra_cflags:
        args.extra_cflags = [flag for flags in args.extra_cflags for flag in shlex.split(flags)]
    
    cfg_path = Path(repo_path) / "config.toml"
    if cfg_path.exists():
        for k, v in toml.load(cfg_path).items():
            if hasattr(cfg, k):
                assert type(getattr(cfg, k)) == type(v), f"Type mismatch for {k}. Expected {type(getattr(cfg, k))}, got {type(v)}."
                setattr(cfg, k, v)
    
    for k, v in vars(args).items():
        if v is not None and hasattr(cfg, k):
            assert type(getattr(cfg, k)) == type(v), f"Type mismatch for {k}. Expected {type(getattr(cfg, k))}, got {type(v)}."
            setattr(cfg, k, v)

    if envs.sandbox:
        envs.bwrap = shutil.which("bwrap")
        assert envs.bwrap is not None, (
            "Compiler sandbox requires bubblewrap (bwrap), but it was not found in PATH."
        )
        check_bwrap()

    if files or args.output:
        envs.random_filename = False
    
    if cfg.verbose:     # print configurations
        table = Table(show_header=False, box=None, highlight=True)
        table.add_column(justify="right", style="yellow italic")
        table.add_column()
        for k in sorted(vars(envs)):
            table.add_row(k, str(getattr(envs, k)))
        print(Panel(table, title="Environment Configurations", title_align='left', expand=True, highlight=True, border_style="blue"))
        table = Table(show_header=False, box=None, highlight=True)
        table.add_column(justify="right", style="yellow italic")
        table.add_column()
        for k in sorted(vars(cfg)):
            table.add_row(k, str(getattr(cfg, k)))
        print()
        print(Panel(table, title="Test Configurations", title_align='left', expand=True, highlight=True, border_style="blue"))
    
    failed = False
    try:
        if args.phase == "local":
            # Local mode: original full behavior
            test_lab(repo_path, lab, files)
        elif args.phase == "public":
            test_lab(repo_path, lab, files)
        elif args.phase == "hidden":
            if lab not in ("lab2", "lab3", "lab4"):
                # No hidden tests for this lab; write empty result
                save_phase_result(lab, "hidden", 0, 0, envs.output_dir)
                print(f"Hidden tests not applicable for {lab}, skipping.")
            else:
                assert args.hidden_dir, "--hidden-dir is required with --phase hidden"
                test_lab(repo_path, lab, files, hidden_dir=args.hidden_dir)
        elif args.phase == "score":
            score_phase(lab, repo_path, envs.output_dir,
                        args.public_weight, args.hidden_weight)
    except AssertionError as e:
        print(red(f"Error: {e}"))
        failed = True
    if not files and (args.phase == "local" or args.phase == "score"):
        if lab != 'lab0' and not (Path(repo_path) / "reports" / f"{lab}.pdf").exists():
            print(red(f"Error: reports/{lab}.pdf not found."))
            failed = True
        print(f"[bold]Test score: {test_score:.2f}[/bold]")
    print(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S %Z"))
    
    sys.exit(1 if failed else 0)
