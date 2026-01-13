import os
import nuke

def debug_aitor_paths():
    """Print debugging information about Aitor Echeveste plugin paths"""
    print("\n=== DEBUGGING AITOR ECHEVESTE PATHS ===\n")

    # Get all plugin paths
    paths = nuke.pluginPath()

    # Find Aitor paths
    ae_paths = [p for p in paths if "Aitor_Echeveste" in p]

    # Check each path
    for i, path in enumerate(ae_paths):
        print(f"Path {i+1}: {path}")

        # Check if path exists
        if os.path.exists(path):
            print(f"  ✓ Path exists")

            # List gizmo files if any
            try:
                files = [f for f in os.listdir(path) if f.endswith('.gizmo')]
                if files:
                    print(f"  ✓ Gizmos found: {files}")
                else:
                    print(f"  ℹ No gizmo files in this directory")
            except Exception as e:
                print(f"  ✗ Error accessing directory: {e}")
        else:
            print(f"  ✗ PATH DOESN'T EXIST!")

            # Try to diagnose path issues
            if "\\\\" in path:
                print(f"  ℹ Path contains double backslashes which might cause problems")
                fixed_path = path.replace("\\\\", "/")
                print(f"  ℹ Suggested fix: {fixed_path}")
                if os.path.exists(fixed_path):
                    print(f"  ✓ Fixed path exists and is valid!")

    print("\n=== END DEBUG INFO ===\n")

def test_ae_nodes():
    """Test creating Aitor Echeveste nodes"""
    print("\n=== TESTING AITOR ECHEVESTE NODES ===\n")

    # List of nodes to test
    nodes = [
        "aeBrokenEdges",
        "aeAnamorphic",
        "aeFiller",
        "aeBrokenShapes",
        "aePowerPin",
        "aeTransform",
        "aeRelight2D",
        "aeRefracTHOR",
        "aeMotionBlur",
        "aePrefMaker",
        "aeUVChart",
        "aeDirtCG",
        "aeShadows"
    ]

    # Try to create each node
    for node_name in nodes:
        try:
            node = nuke.createNode(node_name)
            print(f"✓ {node_name}: Successfully created")
            nuke.delete(node)
        except Exception as e:
            print(f"✗ {node_name}: Failed - {e}")

    print("\n=== END NODE TESTS ===\n")

# Run these functions to debug your Aitor Echeveste plugin setup
# debug_aitor_paths()
# test_ae_nodes()
