# Live Venue Simulation

A Python CLI application that simulates crowd dynamics and staff management for a live venue. This project was built to solve operational bottlenecks such as unequal crowd flow, wasted infrastructure bandwidth, and local staff exhaustion during clustered emergencies.

## Features

- **Dynamic Buffer Deployment (BFS):** Uses a Breadth-First Search distance matrix to find the closest backup volunteer and automatically deploy them when a local checkpoint fails.
- **Priority Pipelining:** Emergency responders are given absolute priority to bypass crowd queues on the narrow path.
- **Proportional Crowd Allocation:** Uses the Hamilton largest-remainder method to divide path slots mathematically based on crowd demand (Stage vs. Stall areas).
- **No-Waste Bandwidth:** If one side of the crowd is blocked by capacity limits, the dynamic pipeline instantly passes their unused path budget to the other side.
- **Round-Robin Dispatching:** Jobs are assigned fairly using a double-ended queue, preventing volunteer burnout.

## Prerequisites

This simulation is built entirely using the Python 3 standard library. No external dependencies or packages are required.

## How to Run

Run the main file from your terminal:

```bash
python main.py
```

The CLI is completely interactive. It will prompt you step-by-step to configure:
1. Crowd demographics (Parents, Performers, Children, Visitors)
2. Staffing counts and Checkpoint locations
3. Physical constraints (Capacities and throughput limits)
4. Incident probabilities and durations

Once setup is complete, simply press **Enter** to advance time tick-by-tick and watch the engine automatically balance crowd queues and dispatch staff.
