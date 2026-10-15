"""Single-GPU reviewed-label LoRA pilot; no paid compute or automatic promotion."""
import argparse
import hashlib
import json
from pathlib import Path
from .generate import outside_repository


def train(data,output,smoke=False):
    import torch
    from datasets import load_dataset
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer
    if not torch.cuda.is_available():raise RuntimeError('Verify Kaggle GPU access before training')
    output=outside_repository(output)
    config=json.loads((Path(__file__).parents[1]/'config.json').read_text())
    files={s:str(Path(data)/(s+'.jsonl')) for s in ('train','validation')}
    ds=load_dataset('json',data_files=files)
    tokenizer=AutoTokenizer.from_pretrained(config['model'])
    for split in ds:
        for row in ds[split]:
            count=len(tokenizer.apply_chat_template(row['prompt']+row['completion'],tokenize=True))
            if count>config['max_length']:raise ValueError('Overlength example; decisive evidence cannot be truncated')
    model=AutoModelForCausalLM.from_pretrained(config['model'],torch_dtype=torch.float16)
    model.config.use_cache=False
    args=SFTConfig(output_dir=str(output),max_length=config['max_length'],seed=config['seed'],
        learning_rate=config['learning_rate'],num_train_epochs=config['epochs'],
        per_device_train_batch_size=1,gradient_accumulation_steps=config['gradient_accumulation'],
        fp16=True,bf16=False,gradient_checkpointing=True,completion_only_loss=True,
        max_steps=2 if smoke else -1,logging_steps=1,report_to='none',save_strategy='epoch')
    trainer=SFTTrainer(model=model,processing_class=tokenizer,args=args,
        train_dataset=ds['train'],eval_dataset=ds['validation'],
        peft_config=LoraConfig(r=config['rank'],lora_alpha=config['alpha'],lora_dropout=config['dropout'],
            target_modules=['q_proj','k_proj','v_proj','o_proj'],task_type='CAUSAL_LM'))
    trainer.train();trainer.save_model(str(output));tokenizer.save_pretrained(str(output))
    (output/'run-manifest.json').write_text(json.dumps({'config':config,'smoke':smoke,
        'base_model_revision':getattr(model.config,'_commit_hash',None),'gpu':torch.cuda.get_device_name(0),'dataset_sha256':{s:hashlib.sha256(Path(f).read_bytes()).hexdigest() for s,f in files.items()}},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--output',required=True);p.add_argument('--smoke',action='store_true');a=p.parse_args();train(a.data,a.output,a.smoke)
