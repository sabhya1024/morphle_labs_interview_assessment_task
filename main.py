"""Venue operations CLI — step-by-step tick simulation."""

from __future__ import annotations

from input_setup import collect_checkpoints_and_managers, collect_setup
from simulation import Simulation, build_layout, create_people


def main() -> None:
    cfg = collect_setup()
    layout, catalog = build_layout(
        n_gates=cfg["n_gates"],
        n_stalls=cfg["n_stalls"],
        cap_stage=cfg["cap_stage"],
        cap_stall_area=cfg["cap_stall_area"],
        cap_desk=cfg["cap_desk"],
        cap_path_storage=cfg["cap_path_storage"],
        stall_caps=cfg["stall_caps"],
        gate_throughputs=cfg["gate_throughputs"],
        path_capacity=cfg["path_capacity"],
    )
    print("\nMap built. Zones:")
    for zid, name in catalog:
        print(f"  {zid}: {name}")

    cp_specs, mgr_assigns, buffer_zones = collect_checkpoints_and_managers(
        n_checkpoints=cfg["n_checkpoints"],
        n_area_mgrs=cfg["n_area_mgrs"],
        n_volunteers_expected=cfg["n_volunteers_expected"],
        zone_catalog=catalog,
        n_buffers=cfg.get("n_buffers", 0),
    )
    people, checkpoints, managers = create_people(
        layout,
        n_parents=cfg["n_parents"],
        n_performers=cfg["n_performers"],
        n_children=cfg["n_children"],
        n_visitors=cfg["n_visitors"],
        n_leads=cfg["n_leads"],
        checkpoint_specs=cp_specs,
        manager_assigns=mgr_assigns,
        buffer_zones=buffer_zones,
    )
    sim = Simulation(
        layout=layout,
        people=people,
        checkpoints=checkpoints,
        managers=managers,
        spawn_p=cfg["spawn_p"],
        durations=cfg["durations"],
        max_ticks=cfg["max_ticks"],
    )
    print("\nSetup complete. Press Enter for each tick (Ctrl+C to abort).\n")
    while sim.tick < sim.max_ticks:
        sim.step()
        print(sim.report())
        print()
        if sim.fire_stop:
            print("Simulation ended: fire / evacuation.")
            return
        try:
            input("Press Enter for next tick...")
        except EOFError:
            print("No interactive input; stopping.")
            return
    print("Simulation ended: max ticks reached.")


if __name__ == "__main__":
    main()
