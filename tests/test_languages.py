import pytest

from snapcode import languages

CASES = {
    "python": "import os\n\ndef main():\n    print(os.getcwd())\n\nif __name__ == '__main__':\n    main()\n",
    "javascript": "const add = (a, b) => a + b;\nconsole.log(add(1, 2));\n",
    "typescript": "interface User {\n  name: string;\n  age: number;\n}\nconst u: User = { name: 'a', age: 1 };\n",
    "java": "public class Main {\n    public static void main(String[] args) {\n        System.out.println(\"hi\");\n    }\n}\n",
    "csharp": "using System;\nnamespace App {\n    class P { static void Main() { Console.WriteLine(\"hi\"); } }\n}\n",
    "cpp": "#include <iostream>\nint main() {\n    std::cout << \"hi\" << std::endl;\n}\n",
    "go": "package main\n\nimport \"fmt\"\n\nfunc main() {\n    x := 1\n    fmt.Println(x)\n}\n",
    "rust": "fn main() {\n    let mut v = Vec::new();\n    v.push(1);\n    println!(\"{:?}\", v);\n}\n",
    "sql": "SELECT name, COUNT(*) FROM users\nWHERE active = 1\nGROUP BY name;\n",
    "bash": "#!/bin/bash\nfor f in *.txt; do\n  echo \"$f\"\ndone\n",
    "json": '{"name": "snapcode", "version": 1}',
    "html": "<!DOCTYPE html>\n<html><body><div class=\"a\">hi</div></body></html>\n",
    "powershell": "Get-ChildItem -Path . | Where-Object { $_.Length -gt 1kb }\n",
}


@pytest.mark.parametrize("expected,code", CASES.items())
def test_detect(expected, code):
    assert languages.detect(code).key == expected


def test_by_key_aliases():
    assert languages.by_key("C#").key == "csharp"
    assert languages.by_key("ts").key == "typescript"
    assert languages.by_key("unknown").key == "text"
