#! /usr/bin/env python
# -*- mode: python; coding: utf-8 -*-

"""new-homework -- Start a new homework assignment

Install a new homework assignment in your assignments repository, by:

1. Creating a directory for the assignment in the homework repository
2. Installing the problem description and relevant files into that directory
3. Creating a new branch for the assignment off the correct base
4. Checking out that branch
5. Committing the basic assignment files to that branch

Run this command from within the homework repository, where the problem bank
repository is a sibling directory (a child of the homework repository's parent
directory). Then it suffices to issue the command

    python3 new-homework.py language hw-name

where hw-name is the assignment name (all lower case, no file extension) as
specified in the problem bank, and language is a programming language: r,
python, or none. For R and Python, template code will be installed containing
unit tests; for 'none'; nothing will be installed.

For vignettes, if you also supply -x (--suffix) you can specify a larger number,
such as when skipping vignette exercises. To avoid reinstalling description and
resource files in later parts, you can add --no-install.

Ordinarily, the script will exit with an error if the assignment branch already
exists, but that can be overridden with --warn-if-exists. It also makes a
stringent check on the repository to ensure that it is indeed a homework
repository. You can also control whether files are installed and whether the
initial commit is made.

"""

import sys
import os
import os.path
import re
import argparse
import shutil
import csv

from contextlib import contextmanager

try:
    from git import Repo
    from git.exc import InvalidGitRepositoryError
except ModuleNotFoundError:
    print("Error: GitPython module is not installed!")
    print("Make sure you install it first:")
    print("pip install GitPython")
    sys.exit(1)

__version__ = '0.4.0'

@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


def die(*msgs):
    for msg in msgs:
        print("\x1b[31;1m[Error]\x1b[0m " + msg, file=sys.stderr)
    sys.exit(1)


def log(msg):
    if verbose:
        print(":: " + msg, file=sys.stderr)


def validate(repo):
    """Check if homework repository is valid. Return repo or None if invalid."""
    # Currently no rules to check
    return repo


def strictly_validate(repo):
    """
    Check if repository and branch name are valid according to strict rules.
    These are:

    + repo has a tag or branch named clean-start

    Return a (boolean, string) pair with (valid?, reason).
    """

    if 'clean-start' not in repo.refs:
        return (False, 'repo does not have a ref named clean-start')

    return (True, '')


def try_repo(maybe_dir, message="Using"):
    """Check if maybe_dir is a git repository."""
    if not os.path.isdir(maybe_dir):
        return None
    try:
        r = Repo(maybe_dir)
        log("{} {} as homework repository".format(message, maybe_dir))
    except InvalidGitRepositoryError:
        r = None
    return r


def guess_repo(starting_dir):
    """Try to find an assignment repo, looking near starting_dir and guessing.

    A matching directory has a name assignments-* and is a git repository.
    The search order is starting_dir, then directories in starting_dir,
    its parents, its grandparents, ~s650.
    """

    home = os.environ['HOME']
    hw_re = re.compile(r'^assignments-')
    guess_dirs = [os.path.abspath(starting_dir),
                  os.path.abspath(os.path.join(starting_dir, '..')),
                  os.path.abspath(os.path.join(starting_dir, '..', '..')),
                  os.path.join(home, 's750'),
                  os.path.join(home, 's650')]

    # Check first where we are and directly above
    for d, name in [(d, os.path.basename(d)) for d in guess_dirs[0:2]]:
        if re.match(hw_re, name) and os.path.isdir(d):
            log("Checking dir {}".format(d))
            r = try_repo(d, "Guessing")
            if r is not None:
                return r

    for dir in guess_dirs:
        try:
            cand = os.listdir(dir)
            for d in [os.path.join(dir, f) for f in cand if re.match(hw_re, f)]:
                if os.path.isdir(d):
                    log("Checking dir {}".format(d))
                    r = try_repo(d, "Guessing")
                    if r is not None:
                        return r
        except OSError:
            pass
    return None


def find_repo(maybe_repo, guess, cwd):
    """Find the assignments respository starting from an initial candidate.


    Parameters:
    + maybe_repo -- if not empty, the repository to use, which must exist
    + guess      -- if true and repo not found, try to guess intelligently
    + cwd        -- current working directory

    """
    repo = None

    if maybe_repo:
        repo = try_repo(maybe_repo)
        if repo is None:
            die('Cannot find specified repository {}'.format(maybe_repo))

    if guess and repo is None:
        repo = guess_repo(cwd)
    if repo is None:
        repo = try_repo(cwd)

    return validate(repo)


def hw_branch_exists(repo, name):
    """Return hw branch ref if it exists, or False."""
    if name in repo.refs:
        return repo.refs[name]
    return False


def auto_branch_name(repo, name, suffix=None):
    """Find the name for an automatically generated vignette branch name.

    If a branch matching name or name with a suffix "-n" for some integer
    n exists, create a branch name with suffix "-m" where m is 2 or n+1,
    respectively. Matching is done case insensitively, and the existing
    branch name (or root) is used. The intended use case is to start
    with a -1 suffix.

    If no matching branch is found, the branch name is of the form name-1.

    Returns a tuple containing the computed branch name, the base branch name to
    which the new branch is a sequel (or None otherwise), the exercise number,
    and a boolean indicating whether the returned branch name represents a
    sequel to an existing branch.
    """

    branch_rx = re.compile(r'(' + name + r')(?:-(\d+))?$', flags=re.IGNORECASE)
    prev = []
    base_name = None
    exercise_no = None

    for b in repo.branches:
        m = re.match(branch_rx, b.name)
        if m and m.group(2):
            prev.append((b.name, m.group(1), int(m.group(2))))

    if prev:
        base_name, root, M = sorted(prev, key=lambda x: x[2], reverse=True)[0]

        if suffix is None or suffix == 0:
            exercise_no = M + 1
        elif suffix > M:
            exercise_no = suffix
        else:
            die("When given, --suffix {} must exceed max branch suffix {}."
                .format(suffix, M))
        hw_name = root + "-" + str(exercise_no)
        sequel = True
        log("On auto, detected previous branch {}, adding {}"
            .format(base_name, hw_name))
    else:
        hw_name = name + '-1'
        exercise_no = 1
        base_name = "master"
        sequel = False

    return (hw_name, base_name, exercise_no, sequel)


def branch_base_dir_names(repo, name, base, is_vignette, num_parts):
    """Set the names for the hw branch, base branch, and hw documents/directory.

    Parameters:
    + repo        -- homework repository (to find branch names)
    + name        -- assignment name as given on the command line
    + base        -- base branch/tag to branch from
    + is_vignette -- is this a vignette?
    + num_parts   -- number of parts in the vignette (1 for stand-alones)

    Return tuple (branch_name, base_name, doc_name, auto-sequel-branch?)
    """

    hw_name, base_name, hdir_name = (name, base, name)
    sequel = False  # Are we building on a previous exercise/branch?

    if is_vignette:
        hw_name, base_name, exercise_no, sequel = auto_branch_name(repo, name)

        if exercise_no > num_parts:
            die("The vignette {} only has {} exercises; cannot create a branch ".format(name, num_parts),
                "for non-existent exercise {}.".format(exercise_no))


    log("Calculated names for branch {}, base {}, dirs {}; is_vignette={}"
        .format(hw_name, base_name, hdir_name, is_vignette))
    return (hw_name, base_name, hdir_name, sequel)


def make_hw_directory(hw_dir, hdir_name):
    try:
        os.mkdir(hdir_name)
        log("Creating directory for work on {}".format(hdir_name))
    except FileExistsError:
        print("Warning: directory {} already exists; continuing anyway..."
              .format(hdir_name), file=sys.stderr)
    # Put a .gitkeep file so the directory is at least tracked
    try:
        with open(os.path.join(hw_dir, '.gitkeep'), 'w') as f:
            print("", file=f)
    except IOError:
        die("Cannot write file in homework directory")


def make_hw_branch(repo, name, base):
    """Create (if new) and checkout the homework branch name."""
    b = hw_branch_exists(repo, name)
    if b:
        repo.refs[name].checkout()
        return b

    if base not in repo.refs:
        die("Base branch {} does not exist".format(base))

    repo.git.checkout(base, b=name)
    return repo.refs[name]


def check_problem_bank(repo_dir, problem_base):
    """Find the local problem bank and check that it is accessible."""
    problem_bank = (problem_base and os.path.abspath(problem_base)) or \
        os.path.normpath(os.path.join(repo_dir, "../problem-bank"))

    if not problem_bank or not os.access(problem_bank, os.R_OK):
        problem_bank = ''
        die("Cannot find problem-bank repository; see --problems option."
            "The problem-bank should be in the same directory as your assignments repository.")

    return problem_bank


def install_problem(name, hw_dir, problem_bank):
    """Move assignment description and related files into our repository.

    If problem_bank is empty, the directory is missing; note in log.

    Return list of installed files and directories (not recursively)
    relative to repository root directory.

    """
    if not problem_bank:
        print("Warning: Missing problem bank, skipping file install.")
        print("To install later, run with --warn-if-exists and, if appropriate, ")
        print("use the --problems option to specify location of the problem bank.")
        return []

    pdf = "{}.pdf".format(name)
    base = ['Data', 'Resources']
    copies = [(os.path.join(problem_bank, d, name),
               os.path.join(hw_dir, d),
               d) for d in base]
    installed = []

    try:
        shutil.copyfile(os.path.join(problem_bank, "All", pdf),
                        os.path.join(hw_dir, pdf))
        installed.append(os.path.join(name, pdf))
    except IOError as e:
        print("Warning: Could not install PDF file from problem bank: "
              "{e.strerror} (errno={e.errno}) file {e.filename}.".format(e=e),
              file=sys.stderr)

    for src, dest, dirname in copies:
        if os.path.isdir(src) and not os.path.exists(dest):
            try:
                shutil.copytree(src, dest)
                installed.append(os.path.join(name, dirname))
            except shutil.Error as errs:
                for (s, d, why) in errs.args[0]:
                    print("Warning: could not copy {s} to {d} ({why})"
                          .format(s=s, d=d, why=why), file=sys.stderr)
    return installed


def safe_assignment_name(name):
    """Convert an assignment name into one safe to use as a filename.

    This is used for template files, e.g. unit testing and source files. The
    primary concern is that assignment names contain hyphens, but filenames with
    hyphens cannot be imported in Python.
    """

    return name.replace("-", "_").strip()


def install_template(language, hdir_name, problem_bank):
    """Install a template into the repository.

    The template contains a source file and a unit test file, with correct names
    so the student can easily run tests and so CI knows how to find the tests.

    We first look in the assignment directory in the problem bank for a template
    specific to this assignment; if no templates exist, we look in the problem
    bank's `.skel` directory.
    """

    if language == "none":
        return

    template_dirs = [
        os.path.join(problem_bank, "Skel", hdir_name, language.lower()),
        os.path.join(problem_bank, ".skel", language.lower())
    ]

    safename = safe_assignment_name(hdir_name)

    for template_dir in template_dirs:
        if not os.path.exists(template_dir):
            continue

        for dirpath, _, filenames in os.walk(template_dir):
            for filename in filenames:
                contents = open(os.path.join(dirpath, filename), "r").read().replace("ASSIGN", safename)

                open(os.path.join(hdir_name,
                                  filename.replace("ASSIGN", safename)), "w").write(contents)

        return

    die("No template exists for --language={}".format(language))


def get_problem_info(name, problem_bank):
    """Check if the problem exists in the bank.

    Dies if the problem does not exist. Return a tuple:
    (is-vignette?, num-parts)
    where non-vignettes have only 1 part.
    """

    f = open(os.path.join(problem_bank, "points.csv"), "r")
    r = csv.reader(f)
    next(r) # skip header row

    problems = [row[0] for row in r]
    f.close()

    count = problems.count(name)

    if count == 0:
        die("Cannot find an assignment named '{}' in the problem bank.".format(name),
            "The name must be spelled exactly as in the problem-bank repo.",
            "Or the assignment is new and you did not pull the latest problem-bank updates.")

    return count > 1, count


# Main Script

parser = argparse.ArgumentParser(description="Install a new homework "
                                 "assignment to the repository.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__[__doc__.index('\n'):])

parser.add_argument("-b", "--base",
                    type=str,
                    default='',
                    help="Starting point at which to create the new assignment branch. "
                    "Defaults to master, the tip of the master branch. Useful if you "
                    "need to manually set up a vignette.")

parser.add_argument("-g", "--guess-repo",
                    default=False,
                    action='store_true',
                    help="If no repo is specified on the command line, "
                    "attempt to find it nearby or in a few likely "
                    "directories below the user's HOME.")

parser.add_argument("--no-commit",
                    default=False,
                    action='store_true',
                    help="Skip initial commit on assignment branch.")

parser.add_argument("--no-install",
                    default=False,
                    action='store_true',
                    help="Skip installation of assignment files.")

parser.add_argument("-p", "--problems",
                    type=str,
                    default="",
                    help="Path of problem-bank repository directory. "
                    "If not supplied, use ../problem-bank from the homework repo.")

parser.add_argument("-r", "--repo",
                    type=str,
                    default="",
                    help="Path to assignments repository directory. "
                    "If not supplied, use a guessed directory if -g option"
                    "is supplied, or the current directory otherwise.")

parser.add_argument("-v", "--verbose",
                    default=False,
                    action='store_true',
                    help="Provide a log of actions taken to standard error.")

parser.add_argument("--version",
                    action='version',
                    version='%(prog)s ' + __version__,
                    help="Show version information and exit.")

parser.add_argument("-w", "--warn-if-exists",
                    default=False,
                    action='store_true',
                    help="Warn without failure if homework branch already exists.")

parser.add_argument("language",
                    help="Language you will use for the assignment. "
                    "The script will install a simple template for that language, "
                    "if it is supported and --no-install is not passed. Valid "
                    "options are 'r', 'python', or 'none' to install no template.")

parser.add_argument("assignment",
                    type=str,
                    help="Name of the homework assignment to create. Use the "
                    "official name from the homework repository, like "
                    "test-this or cow-proximity.")

args = parser.parse_args()
verbose = args.verbose
aname = args.assignment

cwd = os.getcwd()

# Find and check the homework repository
repo = find_repo(args.repo, args.guess_repo, cwd)
if repo is None:
    die("Could not find a valid assignments repository.",
        "Are you running this command from inside your assignments repository?")

valid, why = strictly_validate(repo)
if not valid:
    die("Repository '{0}' fails strict validity checks ({1}).".format(repo.working_tree_dir, why),
        "If this is assessment incorrect, consider using --skip-checks.")

# Sanity-check the problem bank and the assignment they requested.
problem_bank = check_problem_bank(repo.working_tree_dir, args.problems)
is_vignette, num_parts = get_problem_info(aname, problem_bank)

if repo.is_dirty():
    die("Your repository has uncommitted changes.",
        "You must commit or stash all changes before creating a new branch.")

hw_branch, base, hdir_name, sequelp = \
    branch_base_dir_names(repo, aname, args.base or "master", is_vignette,
                          num_parts)

branch_exists = hw_branch_exists(repo, hw_branch)
if branch_exists:
    if args.warn_if_exists:
        print("Branch {} already exists, continuing anyway."
              .format(hw_branch), file=sys.stderr)
    else:
        branch_exists.checkout()
        die("You already have a branch named {}.".format(hw_branch),
            "Checking out branch and exiting with no other action taken.",
            "To continue, re-run with --warn-if-exists; "
            "see options --no-install and --no-commit.")

hw_dir = os.path.join(repo.working_tree_dir, hdir_name)

# Create the branch, install relevant files, and make initial commit
with cd(repo.working_tree_dir):
    branch = make_hw_branch(repo, hw_branch, base)

    if not sequelp:
        make_hw_directory(hw_dir, hdir_name)

        if not args.no_install:
            files = install_problem(hdir_name, hw_dir, problem_bank)
            log('Installed files: {}'.format(", ".join(files)))

            install_template(args.language, hdir_name, problem_bank)

        if not args.no_commit:
            # Add a clean initial commit on the branch with the installed files
            try:
                repo.index.add([hdir_name])
            except OSError as err:
                print(err.filename, err.errno)
                die("Cannot stage installed files in repository", err)
            repo.index.commit("{}".format(hw_branch))
            log("Committing initial state of work on branch {}.".format(hw_branch))
    else:
        log("Sequel branch {} created off branch {}.".format(hw_branch, base))
        log("No commit made on sequel branch {}.".format(hw_branch))

if is_vignette:
    print("Switched to branch '{}' for vignette '{}'.\n"
          "Type 'cd {}' at the shell prompt, and you are ready to work!"
          .format(hw_branch, hdir_name, os.path.relpath(hw_dir, cwd)),
          file=sys.stderr)
else:
    print("Switched to branch {} for assignment {}.\n"
          "Type 'cd {}' at the shell prompt, and you are ready to work!"
          .format(hw_branch, hdir_name, os.path.relpath(hw_dir, cwd)),
          file=sys.stderr)
