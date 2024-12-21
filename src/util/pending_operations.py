pending_writes = {}
write_instance_ids = {}
read_instance_ids = {}


def clean_operation_states(socket_fd: int):
    if socket_fd in pending_writes:
        del pending_writes[socket_fd]
    if socket_fd in read_instance_ids:
        del read_instance_ids[socket_fd]
    if socket_fd in write_instance_ids:
        del write_instance_ids[socket_fd]
