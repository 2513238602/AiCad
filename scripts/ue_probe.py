import unreal

unreal.log("AICAD_UE_PROBE_START")
unreal.log("AICAD_UE_PROBE_PROJECT={}".format(unreal.Paths.project_dir()))
unreal.log("AICAD_UE_PROBE_ENGINE={}".format(unreal.Paths.engine_dir()))
unreal.SystemLibrary.quit_editor()
