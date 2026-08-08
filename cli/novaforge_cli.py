#!/usr/bin/env python3
"""NovaForge AI CLI - Code analysis and AI assistant from your terminal."""

import click
import httpx
import json
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

console = Console()
API_URL = "http://localhost:8000/api/v1"

@click.group()
def cli():
    """NovaForge AI - Enterprise AI Code Assistant"""

@cli.command()
@click.argument("file", type=click.Path(exists=True))
def analyze(file):
    """Analyze a code file"""
    path = Path(file)
    content = path.read_text()
    language = path.suffix.lstrip(".") or "unknown"
    
    with console.status("Analyzing..."):
        resp = httpx.post(f"{API_URL}/code/analyze", json={"content": content, "language": language})
    
    if resp.is_error:
        console.print(f"[red]Error: {resp.text}[/red]")
        return
    
    data = resp.json()
    console.print(Markdown(f"## Analysis of {file}"))
    console.print_json(json.dumps(data, indent=2))

@cli.command()
@click.argument("question")
@click.option("--repo", "-r", help="Repository context")
def ask(question, repo):
    """Ask NovaForge AI a question"""
    payload = {"message": question, "session_id": "cli-session"}
    if repo:
        payload["repo_id"] = repo
    
    with console.status("Thinking..."):
        resp = httpx.post(f"{API_URL}/chat", json=payload)
    
    if resp.is_error:
        console.print(f"[red]Error: {resp.text}[/red]")
        return
    
    data = resp.json()
    console.print(Markdown(data.get("response", "No response")))

@cli.command()
def agents():
    """List available AI agents"""
    resp = httpx.get(f"{API_URL}/agents")
    if resp.is_error:
        console.print(f"[red]Error: {resp.text}[/red]")
        return
    
    agents_data = resp.json()
    table = Table(title="NovaForge AI Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")
    
    for agent in agents_data:
        table.add_row(agent["name"], agent["description"])
    
    console.print(table)

@cli.command()
@click.argument("agent")
@click.argument("input_text")
def run(agent, input_text):
    """Run a specific AI agent"""
    with console.status(f"Running {agent} agent..."):
        resp = httpx.post(f"{API_URL}/agents/{agent}/run", json={"input": input_text})
    
    if resp.is_error:
        console.print(f"[red]Error: {resp.text}[/red]")
        return
    
    console.print_json(json.dumps(resp.json(), indent=2))

@cli.command()
def status():
    """Check NovaForge API status"""
    try:
        resp = httpx.get(f"{API_URL.replace('/api/v1', '')}/health", timeout=5)
        if resp.is_ok:
            console.print("[green]NovaForge API is running[/green]")
            console.print_json(json.dumps(resp.json(), indent=2))
        else:
            console.print(f"[red]API returned {resp.status_code}[/red]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to NovaForge API[/red]")
        console.print(f"Expected at: {API_URL}")

if __name__ == "__main__":
    cli()
