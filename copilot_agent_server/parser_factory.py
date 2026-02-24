from copilot_tools.parser_0920_summary import Parser0920Summary
from copilot_tools.parser_0920_summary_adv import Parser0920SummaryAdv 

def get_parser(parser_name):
    
    parser_name_map = {
        "parser_0922_summary": Parser0920Summary,
        "parser_0920":Parser0920Summary,
        "parser_0920_summary_adv": Parser0920SummaryAdv
    }

    if parser_name in parser_name_map:
        return parser_name_map[parser_name]()
    else:
        raise ValueError(f"Unknown parser name: {parser_name}")

