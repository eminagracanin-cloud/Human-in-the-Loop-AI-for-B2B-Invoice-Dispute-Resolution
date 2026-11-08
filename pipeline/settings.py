"SETTINGS for the pipeline: every threshold is in this one file. The numbers are placeholders - companies should replace them with their own numbers.
"The choices below are the author's and are not from the practitioner interviews. The matching settings for the data generator are at the top of generate_cases.py.
"

#Stage 1: first glance
PRICE_JUMP = 3.0               
AMOUNT_TOLERANCE = 0.01       

#Stage 2: history check
PRICE_TOLERANCE = 0.005        
QTY_TOLERANCE = 0              
TIE_SEED = 2026                

#Stage 3: root cause
OVERBILLED_TOLERANCE = 0.01    
CRM_ERP_PRICE_TOLERANCE = 0.005   
CRM_ERP_QTY_TOLERANCE = 0         

#Evaluation (evaluate.py)
CREDIT_TOLERANCE = 0.01        

#Stage 3 rules and the history reference
RULES_VERSION = "v2"           
HISTORY_REFERENCE = "median"   
DOCUMENTED_UPLIFTS = []

#Automation-bias test (bias_test.py). ALL of these are INVENTED, not measured.
BIAS_SEED = 2026                    
BIAS_CORRUPTION_SHARE = 0.10        
BIAS_QUEUE_REPEATS = 200            
BIAS_POSITION_BINS = 10             
BIAS_CAREFUL_CATCH = 0.90           
BIAS_SKIM_START_CATCH = 0.90        
BIAS_SKIM_DECAY = 0.97              
BIAS_SKIM_FLOOR = 0.20              
BIAS_VISIBILITY = {"wrong_amount": 0.80, "wrong_invoice": 0.70,
                   "wrong_target": 0.60, "contradicts_evidence": 1.00}


def default_config():
    return {"rules_version": RULES_VERSION,
            "history_reference": HISTORY_REFERENCE,
            "price_tolerance": PRICE_TOLERANCE,
            "documented_uplifts": list(DOCUMENTED_UPLIFTS)}
