import os
import glob
import subprocess
import re
import anthropic
from pathlib import Path
from git_manager import GitManager
from typing import List, Dict, Optional
import logging

# 1. Initialize the Anthropic client
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    print("Error: ANTHROPIC_API_KEY environment variable is not set.")
    exit(1)

client = anthropic.Anthropic(api_key=api_key)

# 2. Fetch target exceptions from the environment
exceptions_env = os.environ.get("TARGET_EXCEPTIONS", "java.lang.NullPointerException")
TARGET_EXCEPTIONS = [ex.strip() for ex in exceptions_env.split(",")]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

def get_coding_standards(file_path=".github/scripts/coding-standards.md"):
    """Reads the coding standards from an external markdown file."""
    if os.path.exists(file_path):
        print(f"Loaded coding standards from {file_path}")
        with open(file_path, 'r') as file:
            return file.read()
    else:
        print(f"Warning: {file_path} not found. Proceeding with default AI knowledge.")
        return "Apply general modern Java best practices."

def find_exception_in_reports():
    """Scans Maven surefire reports for target exceptions."""
    reports = glob.glob('target/surefire-reports/*.txt')
    for report in reports:
        with open(report, 'r') as file:
            content = file.read()
            for exc_type in TARGET_EXCEPTIONS:
                if exc_type in content:
                    print(f"Found {exc_type} in report: {report}")
                    return content, exc_type
    return None, None

def extract_failing_file_path(stack_trace):
    """Finds the first project file in the stack trace."""
    match = re.search(r'at ([\w\.]+)\(([\w]+\.java):(\d+)\)', stack_trace)
    if match:
        class_path = match.group(1).replace('.', '/')
        file_name = match.group(2)

        for root, dirs, files in os.walk('.'):
            if file_name in files:
                return os.path.join(root, file_name)
    return None

def generate_fix(file_path, stack_trace, exc_type, coding_standards):
    """Asks Claude to fix the exception using external coding standards."""
    with open(file_path, 'r') as file:
        java_code = file.read()

    # Inject the external standards into the System Prompt
    system_instructions = f"""
    You are a Senior Java Staff Engineer resolving CI/CD pipeline failures. 
    You must strictly adhere to the following Team Coding Standards when writing fixes.
    If you violate these standards, your Pull Request will be rejected.
    
    ### TEAM CODING STANDARDS ###
    {coding_standards}
    """

    user_prompt = f"""
    The following code throws a {exc_type}.
    
    Stack Trace:
    {stack_trace}
    
    Java Code:
    {java_code}
    
    Fix the {exc_type} in the code addressing the root cause indicated by the stack trace.
    Return ONLY the raw, updated Java code. Do not include markdown formatting like ```java.
    """

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=system_instructions,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    fixed_code = message.content[0].text.replace('```java', '').replace('```', '').strip()
    return fixed_code

def create_pr_and_commit(
    git_manager: GitManager,
    fixes_applied: List[Dict]
) -> Optional[str]:
    """
    Create feature branch, commit fixes, push branch,
    and open GitHub Pull Request.
    """

    try:
        if not fixes_applied:
            logger.warning("No fixes supplied.")
            return None

        # Create branch
        branch_name = git_manager.create_branch()

        logger.info(f"Created branch: {branch_name}")

        # Extract files
        fixed_files = [
            fix["file"]
            for fix in fixes_applied
            if "file" in fix
        ]

        if not fixed_files:
            logger.warning("No valid files to commit.")
            return None

        # Commit changes
        commit_success = git_manager.commit_changes(
            files=fixed_files
        )

        if not commit_success:
            logger.warning("Commit failed.")
            return None

        logger.info(
            f"Committed {len(fixed_files)} file(s)"
        )

        # Push branch
        git_manager.push_branch(branch_name)

        logger.info(
            f"Pushed branch: {branch_name}"
        )

        # Create PR
        pr_url = git_manager.create_pr(
            branch_name=branch_name,
            files_changed=fixed_files
        )

        logger.info(f"Created PR: {pr_url}")

        return pr_url

    except Exception as e:
        logger.error(
            f"PR creation workflow failed: {str(e)}"
        )

        return None      

if __name__ == "__main__":

    workspace = Path(os.getcwd())

    git_manager = GitManager(workspace)

    fixes_applied = []

    standards = get_coding_standards(
        ".github/scripts/coding-standards.md"
    )

    stack_trace, exc_type = find_exception_in_reports()

    if stack_trace and exc_type:

        file_path = extract_failing_file_path(
            stack_trace
        )

        if file_path:

            fixed_code = generate_fix(
                file_path,
                stack_trace,
                exc_type,
                standards
            )

            # Write fix
            with open(file_path, "w") as file:
                file.write(fixed_code)

            # Validate
            test_result = subprocess.run(
                ["mvn", "test"],
                capture_output=True,
                text=True
            )

            if test_result.returncode == 0:

                fixes_applied.append({
                    "file": file_path,
                    "exception": exc_type
                })

                pr_url = create_pr_and_commit(
                    git_manager,
                    fixes_applied
                )

                if pr_url:
                    print(f"PR Created: {pr_url}")
                else:
                    print("Failed to create PR.")