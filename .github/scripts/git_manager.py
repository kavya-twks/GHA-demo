#!/usr/bin/env python3
"""
Git Manager Module

Handles all Git operations:
- Branch creation and management
- Committing changes
- Pushing to remote
- Creating pull requests via GitHub CLI

Includes safety checks and proper Git configuration.
"""

import os
import subprocess
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


class GitManager:
    """Manages Git operations for self-healing pipeline."""
    
    def __init__(self, workspace: Path):
        """Initialize Git manager."""
        self.workspace = Path(workspace)
        self._setup_git_config()
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.github_repo = os.environ.get("GITHUB_REPOSITORY", "unknown/repo")
        
        logger.info(f"Git manager initialized for {self.workspace}")
        logger.info(f"Repository: {self.github_repo}")
    
    def _setup_git_config(self):
        """Configure Git for automated commits."""
        try:
            # Set committer identity for automated commits
            self._run_git_command(
                ["config", "--local", "user.name", "github-actions[bot]"],
                "Setting git user name"
            )
            
            self._run_git_command(
                ["config", "--local", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
                "Setting git user email"
            )
            
            # Configure for pushing
            self._run_git_command(
                ["config", "--local", "push.default", "current"],
                "Configuring git push default"
            )
            
            logger.info("Git configured for automated commits")
        
        except Exception as e:
            logger.warning(f"Could not configure git: {str(e)}")
    
    def create_branch(self, prefix: str = "ai-fix") -> str:
        """
        Create a new feature branch for fixes.
        
        Branch naming convention: ai-fix-{timestamp}
        """
        try:
            # Ensure we're on main branch first
            current_branch = self._get_current_branch()
            logger.info(f"Current branch: {current_branch}")
            
            # Create descriptive branch name
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"{prefix}-{timestamp}"
            
            # Check if branch already exists
            if self._branch_exists(branch_name):
                logger.warning(f"Branch {branch_name} already exists")
                branch_name = f"{branch_name}-{int(time.time() % 1000)}"
            
            # Create and checkout new branch
            self._run_git_command(
                ["checkout", "-b", branch_name],
                f"Creating branch {branch_name}"
            )
            
            logger.info(f"✓ Created branch: {branch_name}")
            return branch_name
        
        except Exception as e:
            logger.error(f"Failed to create branch: {str(e)}")
            raise
    
    def commit_changes(
        self, 
        files: List[str],
        message: str = None,
        description: str = None
    ) -> bool:
        """
        Commit changes to the feature branch.
        
        Args:
            files: List of file paths to commit
            message: Commit message (auto-generated if not provided)
            description: Extended commit message
        """
        try:
            if not files:
                logger.warning("No files to commit")
                return False
            
            # Stage files
            for file in files:
                self._run_git_command(
                    ["add", file],
                    f"Staging {file}"
                )
            
            # Generate commit message if not provided
            if not message:
                message = self._generate_commit_message(files)
            
            # Build commit command
            commit_cmd = ["commit", "-m", message]
            
            if description:
                # Add extended commit message
                commit_cmd.extend(["-m", description])
            
            # Commit
            self._run_git_command(commit_cmd, f"Committing changes")
            
            logger.info(f"✓ Committed {len(files)} file(s)")
            logger.info(f"Commit message: {message}")
            return True
        
        except subprocess.CalledProcessError as e:
            if "nothing to commit" in str(e):
                logger.warning("Nothing to commit")
                return True  # Not an error
            logger.error(f"Failed to commit: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Failed to commit: {str(e)}")
            return False
    
    def push_branch(self, branch_name: str) -> bool:
        """
        Push feature branch to remote.
        
        Args:
            branch_name: Name of branch to push
        """
        try:
            # Push to origin
            self._run_git_command(
                ["push", "origin", branch_name, "--set-upstream"],
                f"Pushing {branch_name} to origin"
            )
            
            logger.info(f"✓ Pushed branch: {branch_name}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to push branch: {str(e)}")
            raise
    
    def create_pr(
        self, 
        branch_name: str, 
        files_changed: List[str],
        base_branch: str = None
    ) -> Optional[str]:
        """
        Create a pull request using GitHub CLI.
        
        Args:
            branch_name: Feature branch name
            files_changed: List of files changed
            base_branch: Target branch (default: master/main)
        
        Returns:
            PR URL if successful, None otherwise
        """
        try:
            # Determine base branch
            if not base_branch:
                base_branch = self._get_base_branch()
            
            # Generate PR title and body
            pr_title, pr_body = self._generate_pr_content(files_changed, branch_name)
            
            logger.info(f"Creating PR: {pr_title}")
            logger.debug(f"PR Body:\n{pr_body}")
            
            # Create PR using GitHub CLI
            pr_url = self._create_pr_with_gh_cli(
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base=base_branch
            )
            
            if pr_url:
                logger.info(f"✓ PR created: {pr_url}")
                return pr_url
            else:
                logger.warning("Could not create PR")
                return None
        
        except Exception as e:
            logger.error(f"Failed to create PR: {str(e)}")
            return None
    
    def _create_pr_with_gh_cli(
        self, 
        title: str, 
        body: str, 
        head: str, 
        base: str
    ) -> Optional[str]:
        """Create PR using GitHub CLI (gh)."""
        try:
            # Ensure GH_TOKEN is set
            if self.github_token:
                os.environ["GH_TOKEN"] = self.github_token
            
            # Create PR
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", title,
                    "--body", body,
                    "--head", head,
                    "--base", base,
                    "--repo", self.github_repo
                ],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Extract PR URL from output
                pr_url = result.stdout.strip()
                return pr_url
            else:
                logger.error(f"gh pr create failed: {result.stderr}")
                return None
        
        except FileNotFoundError:
            logger.error("GitHub CLI (gh) not found. Install with: brew install gh")
            return None
        except Exception as e:
            logger.error(f"Failed to create PR with gh cli: {str(e)}")
            return None
    
    def _generate_pr_content(self, files_changed: List[str], branch_name: str) -> tuple:
        """Generate PR title and body."""
        num_files = len(files_changed)
        files_list = "\n".join(f"- {f}" for f in files_changed[:5])
        if len(files_changed) > 5:
            files_list += f"\n- ... and {len(files_changed) - 5} more"
        
        title = f"🤖 AI Auto-Fix: Resolved test failures ({num_files} file{'s' if num_files > 1 else ''})"
        
        body = f"""## Automated Fix Generated by AI Self-Healer

This pull request was automatically generated to fix test failures detected during the CI pipeline.

### What Was Fixed
- Test failures in the build

### Files Changed
{files_list}

### How It Works
1. The CI pipeline detected test failures
2. AI analysis was performed using Anthropic Claude
3. Fixes were generated and validated
4. This PR was automatically created

### ⚠️ Review Required
**Please review this PR carefully before merging:**
- Verify the fixes are correct and don't introduce new issues
- Check that tests pass locally
- Ensure code quality standards are met
- Run the full test suite to validate

### GitHub Actions
- [View Workflow Run](https://github.com/{self.github_repo}/actions/runs/{os.environ.get('CI_RUN_ID', 'unknown')})
- Branch: `{branch_name}`

---
*This PR was generated by the AI Self-Healing Pipeline. Please review thoroughly before merging.*
"""
        
        return title, body
    
    def _generate_commit_message(self, files: List[str]) -> str:
        """Generate descriptive commit message."""
        num_files = len(files)
        
        if num_files == 1:
            file_name = Path(files[0]).name
            return f"🤖 AI Auto-Fix: Resolved error in {file_name}"
        else:
            return f"🤖 AI Auto-Fix: Resolved errors in {num_files} files"
    
    def _run_git_command(
        self, 
        args: List[str], 
        description: str = None
    ) -> str:
        """Execute a git command."""
        try:
            cmd = ["git"] + args
            
            if description:
                logger.debug(f"{description}: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.debug(f"Git command stderr: {result.stderr}")
                raise subprocess.CalledProcessError(
                    result.returncode,
                    cmd,
                    result.stdout,
                    result.stderr
                )
            
            return result.stdout.strip()
        
        except subprocess.TimeoutExpired:
            logger.error(f"Git command timed out: {' '.join(args)}")
            raise
        except Exception as e:
            logger.error(f"Git command failed: {' '.join(args)}")
            raise
    
    def _get_current_branch(self) -> str:
        """Get current branch name."""
        try:
            output = self._run_git_command(
                ["rev-parse", "--abbrev-ref", "HEAD"],
                "Getting current branch"
            )
            return output.strip()
        except Exception:
            return "unknown"
    
    def _get_base_branch(self) -> str:
        """Determine the target base branch."""
        try:
            # Try to get the default branch from remote
            output = self._run_git_command(
                ["symbolic-ref", "refs/remotes/origin/HEAD"],
                "Getting default remote branch"
            )
            # Output is like "refs/remotes/origin/main"
            return output.split("/")[-1]
        except Exception:
            # Fall back to common defaults
            for branch in ["main", "master", "develop"]:
                try:
                    self._run_git_command(["rev-parse", f"origin/{branch}"])
                    return branch
                except Exception:
                    continue
        
        return "main"  # Default fallback
    
    def _branch_exists(self, branch_name: str) -> bool:
        """Check if branch exists locally or remotely."""
        try:
            self._run_git_command(["rev-parse", f"--verify", branch_name])
            return True
        except Exception:
            return False
    
    def cleanup_branch(self, branch_name: str) -> bool:
        """Delete feature branch (useful for cleanup)."""
        try:
            # Switch to main branch first
            main_branch = self._get_base_branch()
            self._run_git_command(["checkout", main_branch])
            
            # Delete local branch
            self._run_git_command(["branch", "-D", branch_name])
            
            # Delete remote branch
            self._run_git_command(["push", "origin", "--delete", branch_name])
            
            logger.info(f"Cleaned up branch: {branch_name}")
            return True
        
        except Exception as e:
            logger.warning(f"Could not cleanup branch: {str(e)}")
            return False


class GitDiff:
    """Analyze git diffs to understand changes."""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
    
    def get_staged_changes(self) -> str:
        """Get diff of staged changes."""
        try:
            result = subprocess.run(
                ["git", "diff", "--cached"],
                cwd=self.workspace,
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception as e:
            logger.error(f"Could not get staged diff: {str(e)}")
            return ""
    
    def get_uncommitted_changes(self) -> str:
        """Get diff of uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=self.workspace,
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception as e:
            logger.error(f"Could not get diff: {str(e)}")
            return ""
