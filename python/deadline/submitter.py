import os
import subprocess
import re
import nuke
import DeadlineNukeClient

def get_deadline_command():
    return DeadlineNukeClient.GetDeadlineCommand()

def submit_node(node, priority, dependency_ids=None, batch_name=1):
    deadline_cmd = get_deadline_command()
    script_path = nuke.root().name()
    job_name = f"{os.path.basename(script_path)} [{node.name()}]"
    start, end = int(nuke.root().firstFrame()), int(nuke.root().lastFrame())
   
    chunk_size = 20
    if 'EXR' in node.name() and end <= 30:
        chunk_size = 10
    elif 'MOV' in node.name():
        chunk_size = end

    job_info = [
        f"Name={job_name}",
        f"BatchName={os.path.basename(script_path) if batch_name else ''}",
        "Plugin=Nuke",
        f"Priority={priority}",
        f"Frames={start}-{end}",
        f"ChunkSize={chunk_size}",
        "Pool=nuke", 
        "Group=nuke"
    ]
    
    if dependency_ids: 
        job_info.append(f"JobDependencies={dependency_ids}")

    plugin_info = [
        f"SceneFile={script_path}",
        "Version=14.0", 
        "NukeX=True", 
        "BatchMode=True",
        f"WriteNode={node.name()}", 
        "UseNodeRange=True"
    ]

    # Write files to System Temp
    temp_dir = os.environ["TEMP"] 
    job_file = os.path.join(temp_dir, f"nuke_job_{node.name()}.job")
    plugin_file = os.path.join(temp_dir, f"nuke_plugin_{node.name()}.job")

    with open(job_file, "w") as f: f.write("\n".join(job_info))
    with open(plugin_file, "w") as f: f.write("\n".join(plugin_info))

    cmd = [deadline_cmd, job_file, plugin_file, script_path]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    
    if process.returncode != 0:
        nuke.tprint(f"Error submitting {node.name()}: {stderr.decode()}")
        return None

    match = re.search(r"JobID=([a-z0-9]+)", stdout.decode())
    return match.group(1) if match else None

def main_submit():
    sel = nuke.selectedNodes('Write')
    exr = next((n for n in sel if n.name() == "EXR"), None)
    mov = next((n for n in sel if n.name() == "MOV"), None)

    if len(sel) == 1 and exr:
        nuke.scriptSave()
        exr_id = submit_node(exr, 100, batch_name=0)
        if not exr_id:
            return
        nuke.tprint(f"EXR Submitted to Deadline: {exr_id}")
        nuke.message(f"Job Submitted to Deadline\nEXR: {exr_id}")
        return

    if not exr or not mov:
        nuke.message("Select both EXR and MOV nodes.")
        return

    read_node = mov.input(0)
    for i in range(5):
        if not read_node:
            break
        if read_node.Class() == "Read":
            break
        read_node = read_node.input(0)

    if not read_node or read_node.Class() != "Read":
        nuke.message("MOV node is not connected to a Read node.")
        return

    nuke.scriptSave()
    exr_id = submit_node(exr, 99)
    
    if not exr_id:
        return
    nuke.tprint(f"EXR Submitted: {exr_id}")

    exr_path = exr['file'].value()
    read_node['file'].setValue(exr_path)
    
    start, end = nuke.root().firstFrame(), nuke.root().lastFrame()
    read_node['first'].setValue(start)
    read_node['last'].setValue(end)
    read_node['origfirst'].setValue(start)
    read_node['origlast'].setValue(end)
    read_node['colorspace'].setValue("scene_linear")

       
    nuke.scriptSave() # CRITICAL: Save new path to disk for MOV job
    nuke.tprint(f"Updated Read node to: {exr_path}")

    mov_id = submit_node(mov, 100, dependency_ids=exr_id)
    nuke.tprint(f"MOV Submitted: {mov_id}")
    if mov_id:
        nuke.message(f"Jobs Submitted to Deadline\nEXR: {exr_id}\nMOV: {mov_id}")
