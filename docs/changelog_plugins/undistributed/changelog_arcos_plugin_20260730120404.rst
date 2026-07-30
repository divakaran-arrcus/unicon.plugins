--------------------------------------------------------------------------------
New
--------------------------------------------------------------------------------
* ARCOS
    * Added the ArcOS (``os='arcos'``) unicon connection plugin for Arrcus
      ArcOS devices (single-RP), listed in the supported platforms table.
        * ``ArcosSingleRpConnection`` / ``ArcosConnectionProvider``: connects
          via SSH into a Linux bash shell and transitions to the network CLI
          with the ``cli`` command; connection dialog handles confirmation
          prompts and "Press RETURN to get started".
        * ``ArcosStateMachine``: hierarchical bash / enable / config
          statemachine.
            * bash (``root@host:~#``) <-> enable (``root@host#``) via
              ``cli`` / ``exit``.
            * enable <-> config (``root@host(config)#``) via ``config`` /
              ``end``.
            * config -> bash uses a combined ``end`` + ``exit`` transition.
            * Both config-exit paths run a dialog that auto-answers
              "Uncommitted changes found, commit them?" with ``no`` so
              state transitions never stall on an implicit commit prompt.
        * ``ArcosPatterns`` / ``ArcosSettings`` / ``ArcosStatements``: prompt
          patterns for bash/enable/config, confirm and uncommitted-changes
          prompts, error patterns (``% Error``, ``Aborted:``, ``Commit
          failed``, etc.), and settings for connection/commit/config
          timeouts (``COMMIT_TIMEOUT`` defaults to 300s for long-running
          commits such as flex-algo admin-group changes).
        * ``Execute`` service: strips the trailing ArcOS prompt from output
          so JSON (``| display json``) output is returned clean for
          parsing.
        * ``Configure`` service: sends config commands via the generic
          Configure service, then auto-commits (``commit=True`` by default,
          disable with ``commit=False``) using raw ``spawn.expect()``
          instead of dialog processing, so confd spinner characters
          (``\\``, ``|``, ``/``, ``-``) can never falsely match a
          terminal pattern. Handles direct ``Commit complete``, a
          blocking ``Proceed? [yes,no]`` prompt (answers ``yes``), and
          commit failure (sends ``abort`` and raises
          ``SubCommandFailure``), always leaving the device in a known
          state (``config`` or ``enable``) afterwards.
        * ``Load`` service (``device.load(remote_path)``): stages
          ``load override <remote_path>`` then ``commit`` then ``end``,
          matching the load stage's success ("N KiB parsed in N sec") or
          error line, then matching only "Commit complete" (or a
          blocking ``Proceed? [yes,no]`` prompt) for the commit stage,
          with a commit failure inferred via timeout rather than a
          literal ``Aborted:`` match, and buffer draining to avoid async
          subsystem-restart messages (``Aborted:``, ``Subsystem
          stopped:``) bleeding into the commit match. On failure sends
          ``abort`` and raises ``SubCommandFailure``, always returning
          the state machine to ``enable``.
        * ``Rollback`` service (``device.rollback(sno=0)``): stages
          ``rollback configuration <sno>`` then ``commit`` then ``end``,
          with the same commit-complete/proceed handling (a commit
          failure is likewise inferred via timeout, not a literal
          ``Aborted:`` match) and guaranteed end-state as ``Load``.
        * Mock-based unit tests: connect/execute smoke tests, plus
          dedicated config-mode statemachine transition and Configure
          service tests (with and without auto-commit), in
          ``tests/test_plugin_arcos.py`` against a new
          ``tests/mock_data/arcos/arcos_mock_data.yaml`` mock device
          extended with a config state; Load service success, failure,
          and timeout tests in ``arcos/tests/test_arcos_load_service.py``.
