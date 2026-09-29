class ModelManager:
    def __init__(self):
        pass

    def load_model(self, model_name: str = "facebook/opt-125m"):
        from transformers import AutoTokenizer, AutoModelForCausalLM

        # Load model and tokenizer
        model = AutoModelForCausalLM.from_pretrained(model_name)
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        return model, tokenizer
