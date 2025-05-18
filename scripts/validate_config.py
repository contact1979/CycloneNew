"""Configuration validation script.

Validates the entire configuration setup including:
- YAML config file syntax and required fields
- Environment variables
- Azure Key Vault connectivity (if configured)
- Database connectivity
- Exchange API credentials
"""
import asyncio
import sys
from pathlib import Path
from typing import List, Tuple
import ccxt
import psycopg2
from hydrobot.config.settings import settings, load_secrets_into_settings

def validate_trading_pairs() -> List[Tuple[str, str]]:
    """Validate configured trading pairs exist on the exchange."""
    issues = []
    try:
        exchange_class = getattr(ccxt, settings.exchange.name)
        exchange = exchange_class({
            'enableRateLimit': True,
            'timeout': 30000,
        })
        exchange.load_markets()
        
        for pair in settings.exchange.trading_pairs:
            if pair not in exchange.markets:
                issues.append((
                    'error',
                    f"Trading pair {pair} not available on {settings.exchange.name}"
                ))
    except Exception as e:
        issues.append(('error', f"Failed to validate trading pairs: {str(e)}"))
    return issues

def validate_database_connection() -> List[Tuple[str, str]]:
    """Test database connectivity."""
    issues = []
    try:
        conn = psycopg2.connect(settings.database.connection_string)
        conn.close()
    except Exception as e:
        issues.append(('error', f"Database connection failed: {str(e)}"))
    return issues

async def validate_exchange_credentials() -> List[Tuple[str, str]]:
    """Validate exchange API credentials."""
    issues = []
    
    if not settings.exchange.api_key or not settings.exchange.api_secret:
        issues.append(('error', "Exchange API credentials not configured"))
        return issues
    
    try:
        exchange_class = getattr(ccxt, settings.exchange.name)
        exchange = exchange_class({
            'apiKey': settings.exchange.api_key.get_secret_value(),
            'secret': settings.exchange.api_secret.get_secret_value(),
            'enableRateLimit': True,
            'timeout': 30000,
        })
        
        # Test API connection with authentication
        await exchange.fetch_balance()
        
    except Exception as e:
        issues.append(('error', f"Exchange API validation failed: {str(e)}"))
    finally:
        if 'exchange' in locals():
            await exchange.close()
    
    return issues

def validate_model_paths() -> List[Tuple[str, str]]:
    """Validate model paths exist."""
    issues = []
    model_path = Path(settings.models.save_path)
    
    if not model_path.exists():
        issues.append((
            'warning',
            f"Model save path {model_path} does not exist. Will be created at runtime."
        ))
    
    return issues

async def main():
    """Run all validation checks."""
    print("\n=== HydroBot Configuration Validation ===\n")
    
    # Load secrets first
    print("Loading configuration and secrets...")
    try:
        await load_secrets_into_settings()
        print("✓ Configuration loaded successfully")
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        sys.exit(1)
    
    # Collect all validation issues
    all_issues = []
    
    # Validate trading pairs
    print("\nValidating trading pairs...")
    all_issues.extend(validate_trading_pairs())
    
    # Validate database
    print("Validating database connection...")
    all_issues.extend(validate_database_connection())
    
    # Validate exchange credentials
    print("Validating exchange credentials...")
    all_issues.extend(await validate_exchange_credentials())
    
    # Validate paths
    print("Validating model paths...")
    all_issues.extend(validate_model_paths())
    
    # Report results
    print("\n=== Validation Results ===\n")
    
    errors = [msg for level, msg in all_issues if level == 'error']
    warnings = [msg for level, msg in all_issues if level == 'warning']
    
    if errors:
        print("Errors:")
        for error in errors:
            print(f"  ✗ {error}")
    
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  ! {warning}")
    
    if not errors and not warnings:
        print("✓ All validation checks passed successfully!")
        sys.exit(0)
    elif errors:
        print("\n✗ Validation failed with errors")
        sys.exit(1)
    else:
        print("\n! Validation passed with warnings")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())