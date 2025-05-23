"""Configuration management utility.

Helps with backing up, restoring, and migrating configurations between environments.
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

CONFIG_DIR = Path(__file__).parent.parent / "config"


def backup_config(backup_dir: Optional[Path] = None) -> Path:
    """Create a backup of current configuration files."""
    if backup_dir is None:
        backup_dir = CONFIG_DIR / "backups"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_dir / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Backup config.yaml
    config_path = CONFIG_DIR / "config.yaml"
    if config_path.exists():
        shutil.copy2(config_path, backup_dir / "config.yaml")

    # Backup .env if it exists (excluding secrets)
    env_path = CONFIG_DIR / ".env"
    if env_path.exists():
        # Read .env but exclude secret values
        with open(env_path, "r") as f:
            env_lines = f.readlines()

        # Filter out secret values
        safe_env_lines: list[str] = []
        secret_keywords = ["PASSWORD", "SECRET", "KEY", "TOKEN"]
        for line in env_lines:
            if any(keyword in line.upper() for keyword in secret_keywords):
                key = line.split("=")[0] if "=" in line else line.strip()
                safe_env_lines.append(f"{key}=<redacted>\n")
            else:
                safe_env_lines.append(line)

        # Write filtered .env backup
        with open(backup_dir / ".env.backup", "w") as f:
            f.writelines(safe_env_lines)

    print(f"Configuration backed up to: {backup_dir}")
    return backup_dir


def restore_config(backup_path: Path) -> None:
    """Restore configuration from backup."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup directory not found: {backup_path}")

    # Restore config.yaml
    config_backup = backup_path / "config.yaml"
    if config_backup.exists():
        shutil.copy2(config_backup, CONFIG_DIR / "config.yaml")
        print("Restored config.yaml")

    # Restore .env structure (without secrets)
    env_backup = backup_path / ".env.backup"
    if env_backup.exists():
        print("\nEnvironment variables structure restored to .env.example")
        print(
            "Note: Secrets were not restored. Please update the .env file with your actual secrets."
        )
        shutil.copy2(env_backup, CONFIG_DIR / ".env.example")


def create_env_config(environment: str) -> None:
    """Create environment-specific configuration."""
    config_path = CONFIG_DIR / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError("config.yaml not found")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Adjust configuration based on environment
    config["env"] = environment

    if environment == "development":
        config["exchange"]["testnet"] = True
        config["monitoring"]["push_gateway"] = "http://localhost:9091"
        config["database"]["host"] = "localhost"
        config["log_level"] = "DEBUG"
    elif environment == "staging":
        config["exchange"]["testnet"] = True
        config["monitoring"]["push_gateway"] = "http://prometheus-pushgateway:9091"
        config["log_level"] = "INFO"
    elif environment == "production":
        config["exchange"]["testnet"] = False
        config["monitoring"]["push_gateway"] = "http://prometheus-pushgateway:9091"
        config["log_level"] = "INFO"

    # Save environment-specific config
    output_path = CONFIG_DIR / f"config.{environment}.yaml"
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Created environment config: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="HydroBot Configuration Management Utility"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup current configuration")
    backup_parser.add_argument("--dir", type=str, help="Custom backup directory")

    # Restore command
    restore_parser = subparsers.add_parser(
        "restore", help="Restore configuration from backup"
    )
    restore_parser.add_argument(
        "backup_path", type=str, help="Path to backup directory"
    )

    # Create environment config command
    env_parser = subparsers.add_parser(
        "create-env", help="Create environment-specific configuration"
    )
    env_parser.add_argument(
        "environment",
        choices=["development", "staging", "production"],
        help="Target environment",
    )

    args = parser.parse_args()

    try:
        if args.command == "backup":
            backup_dir = Path(args.dir) if args.dir else None
            backup_config(backup_dir)

        elif args.command == "restore":
            restore_config(Path(args.backup_path))

        elif args.command == "create-env":
            create_env_config(args.environment)

        else:
            parser.print_help()

    except Exception as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
