import discord
from discord.ext import commands
import os
from datetime import datetime, timedelta
import re
import subprocess
import logging
from typing import Optional, Tuple, List
from dotenv import dotenv_values

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(name)s][%(levelname)s] - %(message)s",
)
logger = logging.getLogger(__name__)


config = dotenv_values(".env")
# Configuration
VAULT_PATH = config["VAULT_PATH"]
AGENDA_FILE = config["AGENDA_FILE"]
# ALLOWED_USERS = []  # Add your Discord user ID here
TOKEN = config["DISCORD_BOT_TOKEN"]


def run_git_command(command: List[str]) -> Tuple[bool, str]:
    """Run a git command and return the result."""
    try:
        result = subprocess.run(
            command, cwd=VAULT_PATH, capture_output=True, text=True, check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, f"Git error: {e.stderr}"


class TaskBot(commands.Bot):
    def __init__(self):
        # Create intents object
        intents = discord.Intents.default()
        intents.message_content = True  # This is the privileged intent we need
        intents.guilds = True  # To ensure the bot can see guilds/servers
        intents.messages = True  # To ensure the bot can see messages

        super().__init__(command_prefix="!", intents=intents)
        self.add_commands()

    def add_commands(self):
        """Add bot commands."""

        @self.command(name="task")
        async def add_task(ctx, *, task_text: str):
            """
            Add a new task to the agenda. Format: !task task description ::Xd

            Example: !task Write report ::3d
            """
            try:
                # Parse due date if provided
                due_date_match = re.search(r"::\s*(\d+)d", task_text)
                if due_date_match:
                    days = int(due_date_match.group(1))
                    task_text = task_text.replace(due_date_match.group(0), "").strip()
                    due_date = (datetime.now() + timedelta(days=days)).strftime(
                        "%Y-%m-%d"
                    )
                else:
                    due_date = None

                success, message = await self.handle_task_command(task_text, due_date)
                await ctx.send(message)
            except Exception as e:
                logger.error(f"Error adding task: {str(e)}")
                await ctx.send(f"❌ Error adding task: {str(e)}")

        @self.command(name="tasks")
        async def list_tasks(ctx):
            """List all open tasks. Format: !tasks"""
            try:
                tasks = self.get_open_tasks()
                if not tasks:
                    await ctx.send("No open tasks found.")
                    return

                message = "📋 **Open Tasks:**\n\n"
                for task in tasks:
                    if task == "":
                        continue

                    due_date_match = re.search(r"📅 (\d{4}-\d{2}-\d{2})", task)
                    due_date = (
                        f"(Due: {due_date_match.group(1)})" if due_date_match else ""
                    )

                    clean_task = re.sub(r"- \[ \] #task", "", task)
                    clean_task = re.sub(r"➕ \d{4}-\d{2}-\d{2}", "", clean_task)
                    clean_task = re.sub(r"📅 \d{4}-\d{2}-\d{2}", "", clean_task)
                    clean_task = clean_task.strip()

                    message += f"• {clean_task} {due_date}\n"

                if len(message) > 2000:
                    messages = [
                        message[i : i + 1900] for i in range(0, len(message), 1900)
                    ]
                    for msg in messages:
                        await ctx.send(msg)
                else:
                    await ctx.send(message)

            except Exception as e:
                logger.error(f"Error listing tasks: {str(e)}")
                await ctx.send(f"❌ Error listing tasks: {str(e)}")

        @self.command(name="complete")
        async def complete_task(ctx, *, search_text: str):
            """Complete a task using longest prefix match. Format: !complete task description"""
            try:
                if len(search_text) < 3:
                    await ctx.send("❌ Search text must be at least 3 characters long.")
                    return

                tasks = self.get_open_tasks()
                best_match = None
                best_match_length = 0

                for task in tasks:
                    clean_task = re.sub(r"- \[ \] #task", "", task)
                    clean_task = re.sub(r"➕ \d{4}-\d{2}-\d{2}", "", clean_task)
                    clean_task = re.sub(r"📅 \d{4}-\d{2}-\d{2}", "", clean_task)
                    clean_task = clean_task.strip().lower()

                    if (
                        clean_task.startswith(search_text.lower())
                        and len(clean_task) > best_match_length
                    ):
                        best_match = task
                        best_match_length = len(clean_task)

                if not best_match or len(best_match) < 3:
                    await ctx.send(
                        f"❌ No matching task found for '{search_text}'. Try more characters."
                    )
                    return

                success, message = await self.complete_task_in_file(best_match)
                await ctx.send(message)

            except Exception as e:
                logger.error(f"Error completing task: {str(e)}")
                await ctx.send(f"❌ Error completing task: {str(e)}")

        @self.command(name="examples")
        async def show_help(ctx):
            """Show help information about available commands."""
            help_text = """
            📚 **Task Bot Commands**

            `!task <description> [::Xd]`
            Add a new task. Optionally specify due date in X days using ::Xd
            Example: `!task Buy groceries ::3d`

            `!tasks`
            List all open tasks with their due dates

            `!complete <description>`
            Complete a task that matches the description (minimum 3 characters)
            Example: `!complete groceries`

            `!help`
            Show this help message
            """
            await ctx.send(help_text)

    def _restore_file(self, file_path: str, content: str):
        """Restore file to its original content."""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logger.error(f"Error restoring file: {str(e)}")

    async def handle_task_command(
        self, task_text: str, due_date: Optional[str]
    ) -> Tuple[bool, str]:
        """Handle the task command logic with proper rollback on failure."""
        file_path = os.path.join(VAULT_PATH, AGENDA_FILE)

        # Backup current state
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except Exception as e:
            return False, f"Failed to read agenda file: {str(e)}"

        try:
            # Pull latest changes
            success, output = run_git_command(["git", "pull"])
            if not success:
                return False, f"Failed to pull changes: {output}"

            # Format the task
            today = datetime.now().strftime("%Y-%m-%d")
            formatted_task = f"- [ ] #task {task_text} ➕ {today}"
            if due_date:
                formatted_task += f" 📅 {due_date}"

            # Add task to file
            self.add_task_to_file(formatted_task)

            # Git operations
            success, output = run_git_command(["git", "add", AGENDA_FILE])
            if not success:
                self._restore_file(file_path, original_content)
                return False, f"Failed to stage changes: {output}"

            success, output = run_git_command(
                ["git", "commit", "-m", f"Add task: {task_text[:50]}..."]
            )
            if not success:
                self._restore_file(file_path, original_content)
                return False, f"Failed to commit: {output}"

            success, output = run_git_command(["git", "push"])
            if not success:
                self._restore_file(file_path, original_content)
                return False, f"Failed to push: {output}"

            return True, f"✅ Added task: {task_text}" + (
                f" (due: {due_date})" if due_date else ""
            )

        except Exception as e:
            self._restore_file(file_path, original_content)
            logger.error(f"Error in handle_task_command: {str(e)}")
            raise

    async def complete_task_in_file(self, task: str) -> Tuple[bool, str]:
        """Complete a task in the agenda file."""
        file_path = os.path.join(VAULT_PATH, AGENDA_FILE)

        # Backup current state
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.readlines()
        except Exception as e:
            return False, f"Failed to read agenda file: {str(e)}"

        try:
            # Pull latest changes
            success, output = run_git_command(["git", "pull"])
            if not success:
                return False, f"Failed to pull changes: {output}"

            # Update file content
            new_content = []
            task_completed = False
            for line in original_content:
                if line.strip() == task.strip():
                    new_content.append(line.replace("- [ ]", "- [x]"))
                    task_completed = True
                else:
                    new_content.append(line)

            if not task_completed:
                return False, "Task not found in file"

            # Write updated content
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(new_content)

            # Git operations
            success, output = run_git_command(["git", "add", AGENDA_FILE])
            if not success:
                self._restore_file(file_path, "".join(original_content))
                return False, f"Failed to stage changes: {output}"

            # add datetime to commit message
            datetime_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            success, output = run_git_command(
                ["git", "commit", "-m", f"Complete task at {datetime_now}"]
            )
            if not success:
                self._restore_file(file_path, "".join(original_content))
                return False, f"Failed to commit: {output}"

            success, output = run_git_command(["git", "push"])
            if not success:
                self._restore_file(file_path, "".join(original_content))
                return False, f"Failed to push: {output}"

            clean_task = re.sub(r"- \[ \] #task", "", task)
            clean_task = re.sub(r"➕ \d{4}-\d{2}-\d{2}", "", clean_task)
            clean_task = re.sub(r"📅 \d{4}-\d{2}-\d{2}", "", clean_task)
            clean_task = clean_task.strip()

            return True, f"✅ Completed task: {clean_task}"

        except Exception as e:
            self._restore_file(file_path, "".join(original_content))
            logger.error(f"Error in complete_task_in_file: {str(e)}")
            raise

    def add_task_to_file(self, task: str):
        """Add a task to the agenda file."""
        file_path = os.path.join(VAULT_PATH, AGENDA_FILE)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.readlines()

            # Find tasks section
            tasks_start = -1
            for i, line in enumerate(content):
                if line.strip() in ["## Todo", "# Todo"]:
                    tasks_start = i + 1
                    break

            if tasks_start == -1:
                raise ValueError("Tasks section not found in agenda file")

            # Insert task at the top of the tasks section with an extra newline
            content.insert(tasks_start, "\n" + task + "\n")

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(content)

        except Exception as e:
            logger.error(f"Error in add_task_to_file: {str(e)}")
            raise

    def get_open_tasks(self) -> List[str]:
        """Get all open tasks from the agenda file."""
        file_path = os.path.join(VAULT_PATH, AGENDA_FILE)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.readlines()

            tasks = []
            in_tasks_section = False

            for line in content:
                if line.strip() in ["## Todo", "# Todo"]:
                    in_tasks_section = True
                    continue

                if in_tasks_section:
                    if line.strip().startswith("#"):  # New section
                        break
                    if line.strip().startswith("- [ ]"):  # Unchecked task
                        tasks.append(line.strip())

            return tasks

        except Exception as e:
            logger.error(f"Error in get_open_tasks: {str(e)}")
            raise

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"Logged in as {self.user.name} ({self.user.id})")

    async def on_command_error(self, ctx, error):
        """Handle command errors."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Missing required argument. Check command usage.")
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send("❌ Unknown command.")
        else:
            logger.error(f"Command error: {str(error)}")
            await ctx.send(f"❌ An error occurred: {str(error)}")


def main():
    """Main function to run the bot."""
    bot = TaskBot()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
