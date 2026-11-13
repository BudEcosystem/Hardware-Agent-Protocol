from pathlib import Path
import subprocess,json,hashlib,datetime
root=Path(__file__).resolve().parent
entries=[]
selected={
'firmata-protocol': {'protocol.md':'read_full','scheduler.md':'read_full','accelStepperFirmata.md':'not_read'},
'firmata-arduino': {'FirmataParser.cpp':'read_full','examples/StandardFirmata/StandardFirmata.ino':'not_read'},
'rclc': {'rclc/src/rclc/executor.c':'read_selected_sections','rclc_examples/src/example_executor_trigger.c':'read_full'},
}
for name,files in selected.items():
 p=root/'repos'/name
 commit=subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()
 url=subprocess.check_output(['git','-C',str(p),'remote','get-url','origin'],text=True).strip()
 entries.append({'id':name,'url':url,'commit':commit,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checkout_path':str(p.relative_to(root)),'acquisition':'depth-1 git clone; complete checkout at commit, history truncated; no submodules fetched','reading_status':'selected_files_only','files':[{'path':f,'sha256':hashlib.sha256((p/f).read_bytes()).hexdigest(),'reading_status':status} for f,status in files.items()]})
(root/'repositories.json').write_text(json.dumps(entries,indent=2)+'\n')
for e in entries:print(e['id'],e['commit'])
