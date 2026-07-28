#!/usr/bin/env python3
"""Script to pause or resume public queue consumption on a specific invoker node remotely.

This script does NOT need to run inside the worker container or on the worker host.
It only requires network access to the central Redis broker.
"""

import argparse
import os
import sys
from celery import Celery

# Default settings
DEFAULT_REDIS_HOST = "192.168.10.252"
DEFAULT_REDIS_PORT = 23437
DEFAULT_REDIS_DB = 0


def get_celery_app(redis_host, redis_port, redis_db):
    """Initializes the Celery app with the correct broker."""
    redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
    # Use "ml_cluster" to match the worker app name configuration
    return Celery("ml_cluster", broker=redis_url, backend=redis_url)


def manage_worker(worker_ip, action, redis_host, redis_port, redis_db):
    """Sends cancel_consumer or add_consumer commands to a specific worker node."""
    app = get_celery_app(redis_host, redis_port, redis_db)
    
    # Format the target node name
    node_name = f"celery@wyolo_invoker_{worker_ip}"
    
    public_queues = ["gpus_high", "gpus_medium", "gpus_low"]
    
    print("=" * 60)
    print(f"📡 Remote Queue Controller")
    print(f"   Redis Broker : redis://{redis_host}:{redis_port}/{redis_db}")
    print(f"   Target Node  : {node_name}")
    print(f"   Action       : {'PAUSE (Private Only)' if action == 'pause' else 'RESUME (Listen to All)'}")
    print("=" * 60)
    
    # Send control command to destination node
    results = []
    for queue in public_queues:
        if action == "pause":
            # Command to stop consuming from a queue
            response = app.control.cancel_consumer(
                queue,
                destination=[node_name],
                reply=True,
                timeout=2.0
            )
        else:
            # Command to start consuming from a queue
            response = app.control.add_consumer(
                queue,
                destination=[node_name],
                reply=True,
                timeout=2.0
            )
        results.append((queue, response))
        
    # Analyze responses
    print("\nResults:")
    success = False
    for queue, response in results:
        if response:
            for item in response:
                if isinstance(item, dict):
                    for node, status in item.items():
                        print(f"   • Queue '{queue}' on {node}: {status.get('ok', status)}")
                        success = True
                else:
                    print(f"   • Queue '{queue}': {item}")
                    success = True
        else:
            print(f"   • Queue '{queue}': No response from node (node might be offline)")
            
    print("-" * 60)
    if success:
        if action == "pause":
            print(f"✅ Success: Node '{node_name}' is now OUT of public circulation.")
            print(f"   It will only consume from its private queue ({worker_ip}).")
        else:
            print(f"✅ Success: Node '{node_name}' is now BACK in public circulation.")
            print(f"   It will consume from both public and private queues.")
    else:
        print("❌ Failed: No responsive workers found. Check the worker IP and connection.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Remotely pause or resume public queue consumption for a specific invoker node."
    )
    parser.add_argument(
        "--ip",
        required=True,
        help="IP address of the target invoker worker (e.g., 192.168.1.68)"
    )
    parser.add_argument(
        "--action",
        choices=["pause", "resume"],
        required=True,
        help="Action to perform: 'pause' (out of public queues) or 'resume' (back to public queues)"
    )
    parser.add_argument(
        "--redis-host",
        default=os.getenv("CONTROL_HOST", DEFAULT_REDIS_HOST),
        help=f"Redis host address (default: {DEFAULT_REDIS_HOST} or CONTROL_HOST env)"
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=DEFAULT_REDIS_PORT,
        help=f"Redis port (default: {DEFAULT_REDIS_PORT})"
    )
    parser.add_argument(
        "--redis-db",
        type=int,
        default=DEFAULT_REDIS_DB,
        help=f"Redis database index (default: {DEFAULT_REDIS_DB})"
    )

    args = parser.parse_args()
    
    manage_worker(
        worker_ip=args.ip,
        action=args.action,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db
    )


if __name__ == "__main__":
    main()
