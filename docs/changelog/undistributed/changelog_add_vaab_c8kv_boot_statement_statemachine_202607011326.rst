--------------------------------------------------------------------------------
                            New
--------------------------------------------------------------------------------
* iosxe/c8kv/statemachine
    * Added IosXEC8kvSingleRpStateMachine and IosXEC8kvDualRpStateMachine:
        * Added new state machine for C8KV devices to support boot statement 
        recovery.

* iosxe/c8kv/statements
    * Added boot_image statement for C8KV devices:
        * Modified the statement to support C8KV grub> mode by adding send(cmd) 
        instead of sendline. 
