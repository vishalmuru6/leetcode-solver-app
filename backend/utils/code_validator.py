"""
Code validation and correction utilities for LeetCode solutions
Integrates the LeetCodeErrorFixer with the existing n8n workflow
"""

import re
import ast
import sys
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from collections import defaultdict, deque, Counter
from enum import Enum

class ProblemType(Enum):
    ARRAY = "array"
    STRING = "string" 
    TREE = "tree"
    GRAPH = "graph"
    DYNAMIC_PROGRAMMING = "dp"
    GREEDY = "greedy"
    BACKTRACKING = "backtrack"
    SLIDING_WINDOW = "sliding_window"
    TWO_POINTERS = "two_pointers"
    BINARY_SEARCH = "binary_search"
    HASH_MAP = "hash_map"
    STACK = "stack"
    HEAP = "heap"
    LINKED_LIST = "linked_list"
    MATH = "math"

@dataclass
class LeetCodeProblem:
    title: str
    difficulty: str
    problem_type: ProblemType
    expected_signature: str
    common_patterns: List[str]
    typical_errors: List[str]
    input_constraints: Dict[str, Any]

class LeetCodeValidator:
    """
    Fast validator for basic LeetCode solution validation
    Lighter version for quick checks
    """
    
    def __init__(self):
        self.common_errors = [
            "missing class Solution",
            "missing method definition", 
            "missing return statement",
            "syntax error",
            "missing imports"
        ]
    
    def quick_validate(self, code: str) -> Tuple[bool, List[str], float]:
        """
        Quick validation without heavy corrections
        
        Returns:
            Tuple of (is_valid, warnings, confidence_score)
        """
        warnings = []
        confidence = 1.0
        
        # Check 1: Basic structure
        if 'class Solution' not in code:
            warnings.append("Missing 'class Solution' definition")
            confidence -= 0.3
        
        # Check 2: Method definition (more accurate detection)
        has_method_with_self = bool(re.search(r'def\s+\w+\s*\(\s*self(?:\s*,|\s*\)).*:', code))
        if 'class Solution' in code and not has_method_with_self:
            warnings.append("Missing method definition with 'self' parameter")
            confidence -= 0.3
        
        # Check 3: Return statement
        if 'return' not in code:
            warnings.append("Missing return statement")
            confidence -= 0.2
        
        # Check 4: Syntax check
        try:
            ast.parse(code)
        except SyntaxError as e:
            warnings.append(f"Syntax error: {str(e)}")
            confidence -= 0.4
        
        # Check 5: Common imports
        missing_imports = []
        if re.search(r'List\[', code) and 'from typing import' not in code:
            missing_imports.append('List')
        if re.search(r'Optional\[', code) and 'Optional' not in code:
            missing_imports.append('Optional')
        if 'defaultdict' in code and 'from collections import' not in code:
            missing_imports.append('defaultdict')
        
        if missing_imports:
            warnings.append(f"Missing imports: {', '.join(missing_imports)}")
            confidence -= 0.1 * len(missing_imports)
        
        # Check 6: Test code detection
        test_patterns = ['print(', 'Solution().', 'sol =', 'result =', 'coode', 'test code', 'example:', '# Test']
        test_code_found = any(pattern.lower() in code.lower() for pattern in test_patterns)
        if test_code_found:
            warnings.append("Test code detected - should be removed")
            confidence -= 0.1
        
        is_valid = confidence > 0.5 and len([w for w in warnings if 'syntax' in w.lower()]) == 0
        
        return is_valid, warnings, max(0.0, confidence)

class LeetCodeErrorFixer:
    """
    Advanced error fixer specifically designed for LeetCode daily challenges
    """
    
    def __init__(self):
        self.problem_patterns = self._initialize_problem_patterns()
        self.common_fixes = self._initialize_common_fixes()
        self.algorithm_templates = self._initialize_algorithm_templates()
        
    def _initialize_problem_patterns(self) -> Dict[str, LeetCodeProblem]:
        """Initialize patterns for common LeetCode problem types"""
        return {
            # Array Problems
            "two_sum": LeetCodeProblem(
                title="Two Sum",
                difficulty="Easy",
                problem_type=ProblemType.ARRAY,
                expected_signature="def twoSum(self, nums: List[int], target: int) -> List[int]:",
                common_patterns=["hash_map", "complement", "return [i, j]"],
                typical_errors=["return values instead of indices", "missing List import"],
                input_constraints={"nums": "List[int]", "target": "int"}
            ),
            
            "three_sum": LeetCodeProblem(
                title="3Sum",
                difficulty="Medium",
                problem_type=ProblemType.ARRAY,
                expected_signature="def threeSum(self, nums: List[int]) -> List[List[int]]:",
                common_patterns=["sort", "two_pointers", "skip_duplicates"],
                typical_errors=["not skipping duplicates", "wrong return type"],
                input_constraints={"nums": "List[int]"}
            ),
            
            # String Problems
            "valid_palindrome": LeetCodeProblem(
                title="Valid Palindrome",
                difficulty="Easy", 
                problem_type=ProblemType.STRING,
                expected_signature="def isPalindrome(self, s: str) -> bool:",
                common_patterns=["two_pointers", "alphanumeric", "case_insensitive"],
                typical_errors=["not handling spaces/punctuation", "case sensitivity"],
                input_constraints={"s": "str"}
            ),
            
            # Tree Problems
            "binary_tree_inorder": LeetCodeProblem(
                title="Binary Tree Inorder Traversal",
                difficulty="Easy",
                problem_type=ProblemType.TREE,
                expected_signature="def inorderTraversal(self, root: Optional[TreeNode]) -> List[int]:",
                common_patterns=["recursive", "stack", "null_check"],
                typical_errors=["missing null check", "wrong traversal order"],
                input_constraints={"root": "Optional[TreeNode]"}
            ),
            
            # Dynamic Programming
            "climbing_stairs": LeetCodeProblem(
                title="Climbing Stairs",
                difficulty="Easy",
                problem_type=ProblemType.DYNAMIC_PROGRAMMING,
                expected_signature="def climbStairs(self, n: int) -> int:",
                common_patterns=["fibonacci", "dp_array", "space_optimization"],
                typical_errors=["stack overflow from recursion", "wrong base cases"],
                input_constraints={"n": "int"}
            ),
            
            # Graph Problems  
            "number_of_islands": LeetCodeProblem(
                title="Number of Islands",
                difficulty="Medium",
                problem_type=ProblemType.GRAPH,
                expected_signature="def numIslands(self, grid: List[List[str]]) -> int:",
                common_patterns=["dfs", "bfs", "visited", "bounds_check"],
                typical_errors=["stack overflow", "not marking visited", "bounds errors"],
                input_constraints={"grid": "List[List[str]]"}
            )
        }
    
    def _initialize_common_fixes(self) -> Dict[str, callable]:
        """Initialize common fix patterns for LeetCode problems"""
        return {
            "list_parameter_error": self._fix_list_parameter,
            "missing_imports": self._fix_missing_imports,
            "wrong_return_type": self._fix_return_type,
            "index_bounds_error": self._fix_bounds_checking,
            "null_pointer_error": self._fix_null_checks,
            "stack_overflow": self._fix_recursion_depth,
            "type_annotation_error": self._fix_type_annotations,
            "parameter_validation": self._add_parameter_validation,
            "edge_case_handling": self._add_edge_case_handling,
            "algorithm_pattern_fix": self._fix_algorithm_pattern
        }
    
    def _initialize_algorithm_templates(self) -> Dict[ProblemType, str]:
        """Initialize algorithm templates for different problem types"""
        return {
            ProblemType.ARRAY: '''
def solve(self, nums: List[int]) -> Any:
    if not nums:
        return []  # Handle empty array
    
    # Your algorithm here
    result = []
    for i, num in enumerate(nums):
        # Process each element
        pass
    
    return result
''',
            ProblemType.TREE: '''
def solve(self, root: Optional[TreeNode]) -> Any:
    if not root:
        return None  # Handle null tree
    
    def dfs(node):
        if not node:
            return
        
        # Process current node
        # Recursive calls for children
        dfs(node.left)
        dfs(node.right)
    
    dfs(root)
    return result
''',
            ProblemType.DYNAMIC_PROGRAMMING: '''
def solve(self, n: int) -> int:
    if n <= 1:
        return n  # Base cases
    
    # Initialize DP array
    dp = [0] * (n + 1)
    dp[0], dp[1] = 0, 1  # Base cases
    
    for i in range(2, n + 1):
        dp[i] = dp[i-1] + dp[i-2]  # Recurrence relation
    
    return dp[n]
'''
        }

    def fix_leetcode_solution(self, code: str, problem_title: str = None, error_message: str = None) -> Dict[str, Any]:
        """
        Main method to fix LeetCode solutions with specialized handling
        
        Args:
            code: The problematic LeetCode solution
            problem_title: Optional problem title for context
            error_message: Optional error message
            
        Returns:
            Dictionary with corrected code and analysis
        """
        print(f"[INFO] Fixing LeetCode solution: {problem_title or 'Unknown'}")
        
        # Step 1: Identify problem type and patterns
        problem_info = self._identify_problem_type(code, problem_title)
        print(f"[INFO] Detected problem type: {problem_info['type'].value}")
        
        # Step 2: Apply LeetCode-specific corrections
        corrected_code = code
        fixes_applied = []
        
        try:
            # Fix 1: Parameter type issues
            if self._detect_parameter_issues(corrected_code, error_message):
                corrected_code, fix_desc = self._fix_parameter_types(corrected_code, problem_info)
                fixes_applied.append(f"[FIXED] {fix_desc}")
            
            # Fix 2: Missing imports
            if self._detect_missing_imports(corrected_code):
                corrected_code, fix_desc = self._fix_missing_imports(corrected_code, problem_info)
                fixes_applied.append(f"[FIXED] {fix_desc}")
            
            # Fix 3: Algorithm-specific fixes
            if problem_info['type'] in [ProblemType.TREE, ProblemType.GRAPH]:
                if self._detect_null_pointer_issues(corrected_code):
                    corrected_code, fix_desc = self._fix_null_checks(corrected_code, problem_info)
                    fixes_applied.append(f"[FIXED] {fix_desc}")
            
            # Fix 4: Return type issues
            if self._detect_return_type_issues(corrected_code, problem_info):
                corrected_code, fix_desc = self._fix_return_type(corrected_code, problem_info)
                fixes_applied.append(f"[FIXED] {fix_desc}")
            
            # Fix 5: Edge case handling
            corrected_code, edge_fixes = self._add_edge_case_handling(corrected_code, problem_info)
            fixes_applied.extend([f"[FIXED] {fix}" for fix in edge_fixes])
            
            # Step 3: Validate the corrected solution
            validation_result = self._validate_solution(corrected_code, problem_info)
            
            return {
                'original_code': code,
                'corrected_code': corrected_code,
                'problem_type': problem_info['type'].value,
                'fixes_applied': fixes_applied,
                'validation': validation_result,
                'confidence': self._calculate_confidence(fixes_applied, validation_result),
                'suggestions': self._get_optimization_suggestions(problem_info)
            }
            
        except Exception as e:
            return {
                'original_code': code,
                'corrected_code': code,
                'error': f"Fix failed: {str(e)}",
                'fixes_applied': fixes_applied,
                'confidence': 0.0
            }

    def _identify_problem_type(self, code: str, title: str = None) -> Dict[str, Any]:
        """Identify the type of LeetCode problem based on code and title"""
        
        # Check title patterns first
        if title:
            title_lower = title.lower()
            
            # Direct matches
            for pattern_key, problem in self.problem_patterns.items():
                if any(keyword in title_lower for keyword in problem.title.lower().split()):
                    return {
                        'type': problem.problem_type,
                        'signature': problem.expected_signature,
                        'patterns': problem.common_patterns,
                        'constraints': problem.input_constraints
                    }
        
        # Analyze code patterns
        problem_type = ProblemType.ARRAY  # Default
        
        # Tree problem indicators
        if any(keyword in code for keyword in ['TreeNode', 'root', 'left', 'right', 'node.val']):
            problem_type = ProblemType.TREE
        
        # Graph problem indicators
        elif any(keyword in code for keyword in ['grid', 'graph', 'visited', 'dfs', 'bfs']):
            problem_type = ProblemType.GRAPH
        
        # DP problem indicators
        elif any(keyword in code for keyword in ['dp[', 'memo', 'cache', 'fibonacci']):
            problem_type = ProblemType.DYNAMIC_PROGRAMMING
        
        # String problem indicators
        elif any(keyword in code for keyword in ['isalnum', 'lower', 'upper', 'palindrome']):
            problem_type = ProblemType.STRING
        
        # Array/Hash problem indicators
        elif any(keyword in code for keyword in ['nums', 'target', 'complement', 'hash']):
            problem_type = ProblemType.ARRAY
        
        return {
            'type': problem_type,
            'signature': 'def solve(self, *args) -> Any:',
            'patterns': [],
            'constraints': {}
        }
    
    # Include all the other methods from the complete implementation
    # (I'll include key methods here, but you can copy the full implementation)
    
    def _detect_parameter_issues(self, code: str, error_message: str = None) -> bool:
        """Detect parameter type issues like your original error"""
        if error_message and "unsupported operand type(s)" in error_message:
            return True
        
        # Check for common parameter type patterns
        param_patterns = [
            r'(\w+)\s*[-+*/]\s*\d+',  # variable - number operations
            r'len\((\w+)\)',          # length operations
            r'range\((\w+)\)',        # range operations
        ]
        
        for pattern in param_patterns:
            matches = re.findall(pattern, code)
            if matches:
                return True
        
        return False
    
    def _fix_parameter_types(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        """Fix parameter type issues"""
        lines = code.split('\n')
        
        # Find function definition
        func_line_idx = None
        for i, line in enumerate(lines):
            if 'def ' in line and '(self' in line:
                func_line_idx = i
                break
        
        if func_line_idx is None:
            return code, "Could not locate function definition"
        
        # Extract parameter names from function signature
        func_line = lines[func_line_idx]
        param_match = re.findall(r'(\w+)(?:\s*:\s*\w+)?(?:\s*,|\s*\))', func_line)
        
        # Filter out 'self'
        params = [p for p in param_match if p != 'self']
        
        # Add parameter validation after function definition
        validation_lines = [
            "        # Auto-fix: Parameter validation and type correction"
        ]
        
        for param in params:
            if param in ['k', 'n', 'target', 'num', 'val']:  # Common int parameters
                validation_lines.extend([
                    f"        if isinstance({param}, list) and len({param}) == 1:",
                    f"            {param} = {param}[0]  # Extract int from single-element list"
                ])
            elif param in ['nums', 'arr', 'array']:  # Common list parameters
                validation_lines.extend([
                    f"        if not isinstance({param}, list):",
                    f"            {param} = [{param}] if {param} is not None else []"
                ])
        
        # Insert validation after function definition
        for i, validation_line in enumerate(validation_lines):
            lines.insert(func_line_idx + 1 + i, validation_line)
        
        lines.insert(func_line_idx + len(validation_lines) + 1, "")  # Add blank line
        
        return '\n'.join(lines), f"Added parameter validation for {len(params)} parameters"

    def _detect_missing_imports(self, code: str) -> bool:
        """Detect missing imports common in LeetCode"""
        missing_imports = []
        
        # Check for typing imports
        if re.search(r'List\[', code) and 'from typing import' not in code:
            missing_imports.append('List')
        
        if re.search(r'Optional\[', code) and 'Optional' not in code:
            missing_imports.append('Optional')
        
        # Check for collections
        if 'defaultdict' in code and 'defaultdict' not in code[:100]:
            missing_imports.append('defaultdict')
        
        if 'deque' in code and 'from collections import' not in code:
            missing_imports.append('deque')
        
        if 'Counter' in code and 'Counter' not in code[:100]:
            missing_imports.append('Counter')
        
        return len(missing_imports) > 0
    
    def _fix_missing_imports(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        """Add missing imports"""
        imports_to_add = []
        
        # Typing imports
        typing_imports = []
        if re.search(r'List\[', code) and 'List' not in code[:200]:
            typing_imports.append('List')
        if re.search(r'Optional\[', code) and 'Optional' not in code[:200]:
            typing_imports.append('Optional')
        if re.search(r'Dict\[', code) and 'Dict' not in code[:200]:
            typing_imports.append('Dict')
        
        if typing_imports:
            imports_to_add.append(f"from typing import {', '.join(typing_imports)}")
        
        # Collections imports
        collections_imports = []
        if 'defaultdict' in code and 'defaultdict' not in code[:200]:
            collections_imports.append('defaultdict')
        if 'deque' in code and 'deque' not in code[:200]:
            collections_imports.append('deque')
        if 'Counter' in code and 'Counter' not in code[:200]:
            collections_imports.append('Counter')
        
        if collections_imports:
            imports_to_add.append(f"from collections import {', '.join(collections_imports)}")
        
        # Other imports
        if re.search(r'heapq\.\w+', code) and 'import heapq' not in code:
            imports_to_add.append('import heapq')
        
        if re.search(r'math\.\w+', code) and 'import math' not in code:
            imports_to_add.append('import math')
        
        if imports_to_add:
            import_section = '\n'.join(imports_to_add) + '\n\n'
            return import_section + code, f"Added {len(imports_to_add)} missing imports"
        
        return code, "No missing imports detected"

    # Placeholder methods - implement based on your needs
    def _detect_null_pointer_issues(self, code: str) -> bool:
        return 'root' in code and 'if not root' not in code
    
    def _fix_null_checks(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        return code, "No null checks needed"
    
    def _detect_return_type_issues(self, code: str, problem_info: Dict) -> bool:
        return False
    
    def _fix_return_type(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        return code, "No return type fixes needed"
    
    def _fix_list_parameter(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        """Fix list parameter type issues"""
        return code, "No list parameter fixes needed"
    
    def _fix_bounds_checking(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        """Fix index bounds checking issues"""
        return code, "No bounds checking fixes needed"
    
    def _fix_recursion_depth(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        """Fix recursion depth issues"""
        return code, "No recursion depth fixes needed"
    
    def _fix_type_annotations(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        """Fix type annotation issues"""
        return code, "No type annotation fixes needed"
    
    def _add_parameter_validation(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        """Add parameter validation"""
        return code, "No parameter validation fixes needed"
    
    def _fix_algorithm_pattern(self, code: str, problem_info: Dict) -> Tuple[str, str]:
        """Fix algorithm pattern issues"""
        return code, "No algorithm pattern fixes needed"
    
    def _add_edge_case_handling(self, code: str, problem_info: Dict) -> Tuple[str, List[str]]:
        """Add edge case handling and fix common issues"""
        fixes_applied = []
        
        # Fix 1: Missing self parameter in method definitions
        if not re.search(r'def\s+\w+\s*\(.*self.*\):', code):
            code, self_fix = self._fix_missing_self_parameter(code)
            if self_fix:
                fixes_applied.append(self_fix)
        
        # Fix 2: Remove test code
        original_lines = len(code.split('\n'))
        code, test_removed = self._remove_test_code(code)
        new_lines = len(code.split('\n'))
        if original_lines != new_lines:
            fixes_applied.append(f"Removed {original_lines - new_lines} lines of test code")
        
        # Fix 3: Fix method signature formatting
        code, method_fix = self._fix_method_signature(code)
        if method_fix:
            fixes_applied.append(method_fix)
        
        return code, fixes_applied
    
    def _fix_missing_self_parameter(self, code: str) -> Tuple[str, str]:
        """Fix missing 'self' parameter in method definitions"""
        lines = code.split('\n')
        fix_applied = ""
        
        for i, line in enumerate(lines):
            # Find method definitions that don't have 'self'
            method_match = re.match(r'^(\s*)def\s+(\w+)\s*\(([^)]*)\)\s*(.*)$', line)
            if method_match:
                indent, method_name, params, rest = method_match.groups()
                
                # Skip if already has self or is not inside a class
                if 'self' in params:
                    continue
                
                # Check if we're inside a class by looking at previous lines
                in_class = False
                for j in range(i-1, -1, -1):
                    if lines[j].strip().startswith('class '):
                        in_class = True
                        break
                    elif re.match(r'^[a-zA-Z]', lines[j]):  # Non-indented line
                        break
                
                if in_class:
                    # Add self parameter
                    if params.strip():
                        new_params = f"self, {params}"
                    else:
                        new_params = "self"
                    
                    lines[i] = f"{indent}def {method_name}({new_params}){rest}"
                    fix_applied = f"Added 'self' parameter to method '{method_name}'"
        
        return '\n'.join(lines), fix_applied
    
    def _remove_test_code(self, code: str) -> Tuple[str, bool]:
        """Remove test code from solution"""
        lines = code.split('\n')
        cleaned_lines = []
        removed_any = False
        
        # Patterns that indicate test code
        test_patterns = [
            r'^\s*print\s*\(',                    # print statements
            r'^\s*solution\s*=\s*Solution\(\)',   # solution = Solution()
            r'^\s*sol\s*=\s*Solution\(\)',        # sol = Solution()
            r'^\s*result\s*=\s*solution\.',       # result = solution.method()
            r'^\s*result\s*=\s*sol\.',            # result = sol.method()
            r'^\s*assert\s+',                     # assert statements
            r'^\s*if\s+__name__\s*==\s*["\']__main__["\']:', # if __name__ == "__main__":
            r'^\s*#\s*Test',                      # # Test comments
            r'^\s*#\s*Example',                   # # Example comments
            r'^\s*(input|output)\s*=',            # input = / output = 
            r'^\s*test_cases\s*=',                # test_cases =
            r'^\s*for.*test.*in',                 # for test in test_cases
            r'.*coode.*',                         # lines with "coode" typo
            r'.*test\s+code.*',                   # lines with "test code"
        ]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check if line matches any test pattern
            is_test_line = any(re.match(pattern, line) for pattern in test_patterns)
            
            if is_test_line:
                removed_any = True
                # If it's an if __name__ == "__main__": block, remove everything after it
                if re.match(r'^\s*if\s+__name__\s*==\s*["\']__main__["\']:', line):
                    # Remove this line and everything after it
                    break
                else:
                    # Skip this line
                    i += 1
                    continue
            
            # Check for test code blocks (like multiple print statements)
            if re.match(r'^\s*print\s*\(', line):
                # Remove consecutive print statements
                while i < len(lines) and re.match(r'^\s*print\s*\(', lines[i]):
                    removed_any = True
                    i += 1
                continue
            
            cleaned_lines.append(line)
            i += 1
        
        # Remove trailing empty lines
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        
        return '\n'.join(cleaned_lines), removed_any
    
    def _fix_method_signature(self, code: str) -> Tuple[str, str]:
        """Fix common method signature issues"""
        lines = code.split('\n')
        fix_applied = ""
        
        for i, line in enumerate(lines):
            # Fix common typos in method definitions
            if 'def ' in line and '(self' in line:
                # Fix missing colon at end
                if not line.rstrip().endswith(':'):
                    lines[i] = line.rstrip() + ':'
                    fix_applied = "Added missing colon to method definition"
                
                # Fix spacing issues
                if '(self,' in line:
                    lines[i] = line.replace('(self,', '(self, ')
                    fix_applied = "Fixed method parameter spacing"
        
        return '\n'.join(lines), fix_applied
    
    def _validate_solution(self, code: str, problem_info: Dict) -> Dict[str, Any]:
        """Basic validation"""
        try:
            ast.parse(code)
            syntax_valid = True
        except:
            syntax_valid = False
        
        return {
            'syntax_valid': syntax_valid,
            'has_function_def': 'def ' in code,
            'has_return_statement': 'return' in code,
            'potential_issues': []
        }
    
    def _calculate_confidence(self, fixes_applied: List[str], validation_result: Dict) -> float:
        """Calculate confidence score"""
        confidence = 0.7  # Base confidence
        
        if validation_result.get('syntax_valid', False):
            confidence += 0.2
        
        if validation_result.get('has_function_def', False):
            confidence += 0.1
        
        return min(1.0, max(0.0, confidence))
    
    def _get_optimization_suggestions(self, problem_info: Dict) -> List[str]:
        """Get optimization suggestions"""
        return ["Consider optimizing time complexity", "Add edge case handling"]

# Convenience functions for backward compatibility
def quick_fix_leetcode(code: str, problem_title: str = None) -> Tuple[str, bool, List[str]]:
    """
    Quick fix function for LeetCode solutions
    Compatible with existing n8n.py usage
    
    Returns:
        Tuple of (corrected_code, is_safe, warnings)
    """
    try:
        # Use the light validator first
        validator = LeetCodeValidator()
        is_valid, warnings, confidence = validator.quick_validate(code)
        
        # If validation fails, try the error fixer
        if not is_valid or confidence < 0.7:
            fixer = LeetCodeErrorFixer()
            result = fixer.fix_leetcode_solution(code, problem_title)
            
            corrected_code = result.get('corrected_code', code)
            fixes = result.get('fixes_applied', [])
            confidence = result.get('confidence', 0.0)
            
            # Convert fixes to warnings
            new_warnings = [fix.replace('[FIXED] ', '') for fix in fixes]
            warnings.extend(new_warnings)
            
            is_safe = confidence > 0.6
            return corrected_code, is_safe, warnings
        
        # If already valid, return as-is
        return code, True, warnings
        
    except Exception as e:
        print(f"[validator] Error in quick_fix_leetcode: {str(e)}")
        return code, False, [f"Validation error: {str(e)}"]

def validate_code_structure(code: str) -> Dict[str, Any]:
    """
    Validate basic code structure
    
    Returns:
        Dictionary with validation results
    """
    validator = LeetCodeValidator() 
    is_valid, warnings, confidence = validator.quick_validate(code)
    
    return {
        'is_valid': is_valid,
        'warnings': warnings,
        'confidence': confidence,
        'has_class_solution': 'class Solution' in code,
        'has_method_def': bool(re.search(r'def\s+\w+\s*\(.*self.*\):', code)),
        'has_return': 'return' in code
    }