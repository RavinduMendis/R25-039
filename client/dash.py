import requests
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
import typer
from typing import Literal
import subprocess
import sys
import time
import questionary

# Initialize the console for rich output
console = Console()

# The base URL for the client's local API
BASE_URL = "http://127.0.0.1:8000"

# Use typer to create a command-line application
app = typer.Typer(help="A TUI to launch and control the FL client's privacy preferences.")

def is_client_api_ready():
    """Checks if the client's local API server is running."""
    try:
        response = requests.get(f"{BASE_URL}/get_privacy_preference", timeout=1)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def get_current_preference():
    """Fetches the current privacy preference from the client's API."""
    try:
        response = requests.get(f"{BASE_URL}/get_privacy_preference")
        response.raise_for_status()
        data = response.json()
        if data["status"] == "success":
            return data["method"]
        else:
            console.print(f"[red]Error fetching preference: {data['message']}[/red]")
            return "unknown"
    except requests.exceptions.RequestException:
        return "unknown" # Don't print an error if the server is just starting

def set_new_preference(method: Literal["HE", "SSS", "Normal", "NONE"]):
    """Sets a new privacy preference via the client's API."""
    try:
        payload = {"method": method}
        response = requests.post(f"{BASE_URL}/set_privacy_preference", json=payload)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "success":
            if method == "NONE":
                 console.print("[green]Successfully paused the client. Select a method to resume.[/green]")
            else:
                console.print(f"[green]Successfully updated preference to: [bold]{method}[/bold][/green]")
                console.print("[green]The client will use this mode on its next training round.[/green]")
        else:
            console.print(f"[red]Error setting preference: {data['message']}[/red]")
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Could not connect to the client API: {e}[/red]")

@app.command(name="run", help="Starts the client and the interactive TUI.")
def run_tui():
    """Main function to launch the client and run the interactive TUI."""
    console.print(Panel(Text("FLF 2.0 Client Controller", justify="center", style="bold green")))
    
    client_process = None
    log_file = None
    try:
        console.print("[yellow]Attempting to start the client process...[/yellow]")
        console.print("[italic]Client logs are being saved to [bold]client.log[/bold][/italic]")
        log_file = open("client.log", "w") # Use 'w' to overwrite old logs on start
        client_process = subprocess.Popen(
            [sys.executable, "client.py"],
            stdout=log_file,
            stderr=subprocess.STDOUT
        )

        console.print("[yellow]Waiting for client's API to be ready...[/yellow]")
        max_wait = 20
        for _ in range(max_wait):
            if is_client_api_ready():
                console.print("[green]Client API is ready![/green]")
                break
            time.sleep(0.5)
        else:
            console.print("[bold red]Error: Client API did not start in time. Check client.log for errors. Exiting.[/bold red]")
            return

        console.print("[italic]This tool manages the client's privacy preferences.[/italic]")
        console.print("Press Ctrl+C at any time to exit (this will also stop the client).")

        while True:
            console.print("---")
            current_method = get_current_preference()
            
            choices = ["HE", "SSS", "Normal"]
            prompt_message = "Select a new method (use arrow keys and Enter)"

            if current_method == "unknown":
                console.print("[bold red]Could not communicate with client API. Please wait or restart.[/bold red]")
                time.sleep(2)
                continue
            elif current_method == "NONE":
                console.print("[bold yellow]Client is PAUSED. Select a method to GO (start training).[/bold yellow]")
                prompt_message = "Select a method to GO"
            else:
                console.print(f"Current Privacy Method: [bold magenta]{current_method}[/bold magenta]")
                # Add a pause option only if the client is currently running
                choices.append("Pause Client")

            choices.append("Exit")

            choice = questionary.select(
                prompt_message,
                choices=choices
            ).ask()

            if choice is None or choice == "Exit":
                break
            
            # Map the TUI choice to the required API value
            method_to_set = "NONE" if choice == "Pause Client" else choice
            set_new_preference(method_to_set)
    
    except KeyboardInterrupt:
        console.print("\nCtrl+C detected. Shutting down.")
    finally:
        if client_process and client_process.poll() is None:
            console.print("[yellow]Terminating client process...[/yellow]")
            client_process.terminate()
            try:
                client_process.wait(timeout=5)
                console.print("[green]Client process stopped.[/green]")
            except subprocess.TimeoutExpired:
                console.print("[red]Client process did not terminate gracefully. Forcing shutdown.[/red]")
                client_process.kill()
                client_process.wait()
        if log_file:
            log_file.close()
        console.print("Exiting controller.")

if __name__ == "__main__":
    app()