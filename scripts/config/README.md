# Cinderella Configuration System

This directory contains the configuration system for the Cinderella Nuke tools.

## Configuration Files

- `cinderella_config.json`: This is your local configuration file. It contains your specific settings and is not committed to git.

## Setup

[/NOT YET/]: # (1. When you first run the tools, if `cinderella_config.json` doesn't exist, it will be automatically created from the template.)
2. Edit `cinderella_config.json` to set your local paths and preferences.

## Configuration Structure

The configuration file contains:

- Studio-wide settings (studio name, project roots, default settings)
- Project-specific settings (for each project)
- Tool paths (scripts, gizmos, toolsets)
- Version control settings

## Updating

When pulling updates from git, your local `cinderella_config.json` will be preserved. If new configuration options are added to the template, you'll need to manually add them to your local configuration.