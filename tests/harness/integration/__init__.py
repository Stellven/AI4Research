"""S03 N9 — end-to-end integration tests + activation-proof runner.

Exercises the full Code-as-Harness Runtime chain:
    action_contract (N1)
        -> ExecutionBroker.propose_action (N3)
            -> EventLedger.append (N2, with policy from N4)
                -> projections.build_sprint_status (N8)
                    -> activation_proof_runner.broker_coverage (N9)
"""
