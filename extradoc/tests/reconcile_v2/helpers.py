"""Contract-test helpers for the second-generation reconciler.

Every ``reconcile_v2`` test should follow one pattern:

1. build ``base``
2. build ``desired``
3. call ``reconcile_v2.reconcile(base, desired)``
4. normalize returned batches
5. assert exact equality with expected request batches

The mock transport is not the primary oracle for these tests.
"""
