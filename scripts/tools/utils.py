import nuke


def update_old_paths():
    old_paths = ["//192.168.99.25/", "//192.168.99.202/"]
    new_path = "//192.168.99.203/"

    nodes_to_update = []
    for node in nuke.allNodes(recurseGroups=True):
        if node.Class() in ('Read', 'Write'):
            current_path = node['file'].value()
            if not current_path:
                continue

            for old in old_paths:
                if current_path.startswith(old):
                    nodes_to_update.append((node, old))
                    break

    display_list = [f"{node.name()}: {node['file'].value()}" for node, old in nodes_to_update]
    formatted_list = "\n".join(display_list)

    message = (
        f"Found {len(nodes_to_update)} nodes with old paths. Would you like to update them?\n\n"
        f"{formatted_list}"
    )
    if len(nodes_to_update) == 0:
        return
    if not nuke.ask(message):
        return

    updated_count = 0
    for node, old_path_matched in nodes_to_update:
        current_path = node['file'].value()
        updated_path = current_path.replace(old_path_matched, new_path, 1)

        node['file'].setValue(updated_path)
        nuke.tprint(f"Updated node '{node.name()}': path changed to '{updated_path}'")
        updated_count += 1

    nuke.message(f"Successfully updated {updated_count} node(s).")

nuke.addOnScriptLoad(update_old_paths)