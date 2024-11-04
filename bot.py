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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

config = dotenv_values(".env")

# Configuration
VAULT_PATH = "./"  # Update this
AGENDA_FILE = "agenda.md"
# ALLOWED_USERS = []  # Add your Discord user ID here
TOKEN = config["DISCORD_BOT_TOKEN"]

def run_git_command(command: List[str]) -> Tuple[bool, str]:
    """Run a git command and return the result."""
    try:
        result = subprocess.run(
            command,
            cwd=VAULT_PATH,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, f"Git error: {e.stderr}"

class TaskBot(commands.Bot):
    def __init__(self):
        # Create intents object
        intents = discord.Intents.default()
        intents.message_content = True  # This is the privileged intent we need
        intents.guilds = True           # To ensure the bot can see guilds/servers
        intents.messages = True         # To ensure the bot can see messages
        
        super().__init__(command_prefix='!', intents=intents)
        self.add_commands()

    def add_commands(self):
        @self.command(name='task')
        async def add_task(ctx, *, task_text: str):
            """Add a new task to the agenda. Format: !task task description ::Xd"""
            # if ctx.author.id not in ALLOWED_USERS:
            #     await ctx.send("❌ You're not authorized to use this bot.")
            #     return

            try:
                # Parse due date if provided
                due_date_match = re.search(r'::\s*(\d+)d', task_text)
                if due_date_match:
                    days = int(due_date_match.group(1))
                    task_text = task_text.replace(due_date_match.group(0), '').strip()
                    due_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                else:
                    due_date = None

                success, message = await self.handle_task_command(task_text, due_date)
                await ctx.send(message)
            except Exception as e:
                logger.error(f"Error adding task: {str(e)}")
                await ctx.send(f"❌ Error adding task: {str(e)}")

        @self.command(name='tasks')
        async def list_tasks(ctx):
            """List all open tasks."""
            # if ctx.author.id not in ALLOWED_USERS:
            #     await ctx.send("❌ You're not authorized to use this bot.")
            #     return

            try:
                tasks = self.get_open_tasks()
                if not tasks:
                    await ctx.send("No open tasks found.")
                    return

                # Format tasks into a message
                message = "📋 **Open Tasks:**\n\n"
                for task in tasks:
                    due_date_match = re.search(r'📅 (\d{4}-\d{2}-\d{2})', task)
                    due_date = f"(Due: {due_date_match.group(1)})" if due_date_match else ""
                    
                    # Clean up the task text
                    clean_task = re.sub(r'- \[ \] #', '', task)  # Remove checkbox and #
                    clean_task = re.sub(r'➕ \d{4}-\d{2}-\d{2}', '', clean_task)  # Remove creation date
                    clean_task = re.sub(r'📅 \d{4}-\d{2}-\d{2}', '', clean_task)  # Remove due date
                    clean_task = clean_task.strip()

                    message += f"• {clean_task} {due_date}\n"

                # Split message if it's too long
                if len(message) > 2000:
                    messages = [message[i:i+1900] for i in range(0, len(message), 1900)]
                    for msg in messages:
                        await ctx.send(msg)
                else:
                    await ctx.send(message)

            except Exception as e:
                logger.error(f"Error listing tasks: {str(e)}")
                await ctx.send(f"❌ Error listing tasks: {str(e)}")

    async def handle_task_command(self, task_text: str, due_date: Optional[str]) -> Tuple[bool, str]:
        """Handle the task command logic."""
        try:
            # Format the task
            today = datetime.now().strftime("%Y-%m-%d")
            formatted_task = f"- [ ] {task_text} ➕ {today}"
            if due_date:
                formatted_task += f" 📅 {due_date}"

            # Add task to file
            self.add_task_to_file(formatted_task)
            
            # Git operations
            success, output = run_git_command(['git', 'add', AGENDA_FILE])
            if not success:
                return False, f"Failed to stage changes: {output}"

            success, output = run_git_command(['git', 'commit', '-m', f"Add task: {task_text[:50]}..."])
            if not success:
                return False, f"Failed to commit: {output}"

            success, output = run_git_command(['git', 'push'])
            if not success:
                return False, f"Failed to push: {output}"

            return True, f"✅ Added task: {task_text}" + (f" (due: {due_date})" if due_date else "")
            
        except Exception as e:
            logger.error(f"Error in handle_task_command: {str(e)}")
            raise

    def add_task_to_file(self, task: str):
        """Add a task to the agenda file."""
        file_path = os.path.join(VAULT_PATH, AGENDA_FILE)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.readlines()
            
            # Find tasks section
            tasks_start = -1
            for i, line in enumerate(content):
                if line.strip() in ['## Todo', '# Todo']:
                    tasks_start = i + 1
                    break
            
            if tasks_start == -1:
                raise ValueError("Tasks section not found in agenda file")
            
            # Insert task at the top of the tasks section
            content.insert(tasks_start, task + '\n')
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(content)
                
        except Exception as e:
            logger.error(f"Error in add_task_to_file: {str(e)}")
            raise

    def get_open_tasks(self) -> List[str]:
        """Get all open tasks from the agenda file."""
        file_path = os.path.join(VAULT_PATH, AGENDA_FILE)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.readlines()
            
            tasks = []
            in_tasks_section = False
            
            for line in content:
                if line.strip() in ['## Todo', '# Todo']:
                    in_tasks_section = True
                    continue
                    
                if in_tasks_section:
                    if line.strip().startswith('#'):  # New section
                        break
                    if line.strip().startswith('- [ ]'):  # Unchecked task
                        tasks.append(line.strip())
            
            return tasks
                
        except Exception as e:
            logger.error(f"Error in get_open_tasks: {str(e)}")
            raise

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f'Logged in as {self.user.name} ({self.user.id})')
        
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