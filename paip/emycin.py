from __future__ import print_function
import logging

# -----------------------------------------------------------------------------
# Certainty factors

class CF(object):
    """Important certainty factor values."""
    true = 1.0
    false = -1.0
    unknown = 0.0
    cutoff = 0.2

def cf_or(a, b):
    """
    Compute the certainty factor of (A or B), where the certainty factors of A
    and B are a and b, respectively.
    """
    if a > 0 and b > 0:
        return a + b - a * b
    elif a < 0 and b < 0:
        return a + b + a * b
    else:
        return (a + b) / (1 - min(abs(a), abs(b)))

def cf_and(a, b):
    """
    Compute the certainty of (A and B), where the certainty factors of A and B
    are a and b, respectively.
    """
    return min(a, b)

def is_cf(x):
    """Is x a valid certainty factor; ie, is (false <= x <= true)?"""
    return CF.false <= x <= CF.true

def cf_true(x):
    """Do we consider x true?"""
    return is_cf(x) and x > CF.cutoff

def cf_false(x):
    """Do we consider x false?"""
    return is_cf(x) and x < (CF.cutoff - 1)


# -----------------------------------------------------------------------------
# Contexts

class Context(object):
    
    """A type of thing that can be reasoned about."""
    
    def __init__(self, name, initial_data=None, goals=None):
        self.count = 0 # track Instances with numerical IDs
        self.name = name
        self.initial_data = initial_data or [] # params to find out before reasoning
        self.goals = goals or [] # params to find out during reasoning
    
    def instantiate(self):
        """Create and return a unique Instance of the form (ctx_name, id)."""
        inst = (self.name, self.count)
        self.count += 1
        return inst


# -----------------------------------------------------------------------------
# Parameters

class Parameter(object):
    
    """A property type of a context instance."""
    
    def __init__(self, name, ctx=None, parse=lambda x: x, ask_first=False):
        self.name = name
        self.ctx = ctx
        self.parse = parse
        self.ask_first = ask_first
    
    def from_string(self, string):
        return self.parse(string)


# -----------------------------------------------------------------------------
# Conditions
    
# A condition is a statement of the form (param inst op val), read as "the value
# of inst's param parameter satisfies the relation op(v, val)", where param is
# the name of a Parameter object, inst is an Instance created by a Context
# object, op is a function that compares two parameter values to determine if
# the condition is true, and val is the parameter value.  A condition's truth is
# represented by a certainty factor.

def print_condition(condition):
    param, inst, op, val = condition
    name = inst if isinstance(inst, str) else inst[0]
    opname = op.__name__
    return '%s %s %s %s' % (param, name, opname, val)

def eval_condition(condition, values, find_out=None):
    """
    Determines the certainty factor of the condition (param, inst, op, val)
    using a list of values already associated with the param parameter of inst.
    
    If find_out is specified, it should be a function with the signature
    find_out(values, param, inst) and should find more values for (param, inst).
    """
    logging.debug('Evaluating condition [%s] (find_out %s)' %
                  (print_condition(condition), 'ENABLED' if find_out else 'DISABLED'))
    param, inst, op, val = condition
    if find_out:
        find_out(param, inst)
    total = sum(cf for known_val, cf in values.items() if op(known_val, val))
    logging.debug('Condition [%s] has a certainty factor of %f' %
                  (print_condition(condition), total))
    return total

def parse_cond(cond, instances):
    """
    Given a condition (param, ctx, op, val), return (param, inst, op, val),
    where inst is the current instance of the context ctx.
    """
    param, ctx, op, val = cond
    return param, instances[ctx], op, val


# -----------------------------------------------------------------------------
# Values

def get_vals(values, param, inst):
    """Retrieve the dict of val->CF mappings for (param, inst)."""
    return values.setdefault((param, inst), {})

def get_cf(values, param, inst, val):
    """Retrieve the certainty that the value of the parameter param in inst is val."""
    vals = get_vals(values, param, inst)
    return vals.setdefault(val, CF.unknown)

def update_cf(values, param, inst, val, cf):
    """Combine the CF that (param, inst) is val with cf."""
    existing = get_cf(values, param, inst, val)
    updated = cf_or(existing, cf)
    get_vals(values, param, inst)[val] = updated
    

# -----------------------------------------------------------------------------
# Rules

def use_rules(values, instances, rules, find_out=None, track_rules=None):
    """Apply all of the rules to derive new facts; returns True if a rule succeeded."""
    return any([rule.apply(values, instances, find_out, track_rules) for rule in rules])

class Rule(object):
    
    """
    A rule used for deriving new facts.  Has premise and conclusion conditions
    and an associated certainty of the derived conclusions.
    """
    
    def __init__(self, num, premises, conclusions, cf):
        self.num = num
        self.cf = cf
        # conditions are stored with context names, not specific instances
        self.raw_premises = premises 
        self.raw_conclusions = conclusions
    
    def __str__(self):
        prems = map(print_condition, self.raw_premises)
        concls = map(print_condition, self.raw_conclusions)
        templ = 'RULE %d\nIF\n\t%s\nTHEN %f\n\t%s'
        return templ % (self.num, '\n\t'.join(prems), self.cf, '\n\t'.join(concls))
        
    def premises(self, instances):
        return [parse_cond(premise, instances) for premise in self.raw_premises]
    
    def conclusions(self, instances):
        return [parse_cond(concl, instances) for concl in self.raw_conclusions]

    def applicable(self, values, instances, find_out=None):
        """
        Determines the applicability of this rule (represented by a certainty
        factor) by evaluating the truth of each of its premise conditions
        against known values of parameters.
        
        Arguments:
        - values: a dict that maps a (param, inst) pair to a list of known
              values [(val1, cf1), (val2, cf2), ...] associated with that pair.
              param is the name of a Parameter object and inst is the name of
              a Context.
        - instances: a dict that maps a Context name to its current instance.
        - find_out: see eval_condition
        
        """
        # reject early if possible
        for premise in self.premises(instances):
            param, inst, op, val = premise
            vals = get_vals(values, param, inst)
            cf = eval_condition(premise, vals) # don't pass find_out, just use rules
            if cf_false(cf):
                return CF.false
                        
        logging.debug('Determining applicability of rule (\n%s\n)' % self)
        total_cf = CF.true
        for premise in self.premises(instances):
            param, inst, op, val = premise
            vals = get_vals(values, param, inst)
            cf = eval_condition(premise, vals, find_out)
            total_cf = cf_and(total_cf, cf)
            if not cf_true(total_cf):
                return CF.false
        return total_cf

    def apply(self, values, instances, find_out=None, track=None):
        """
        Combines the conclusions of this rule with known values.
        Returns True if this rule applied successfully and False otherwise.
        """
        if track:
            track(self)
        logging.debug('Attempting to apply rule (\n%s\n)' % self)
        cf = self.cf * self.applicable(values, instances, find_out)
        if not cf_true(cf):
            logging.debug('Rule (\n%s\n) is not applicable (%f certainty)' % (self, cf))
            return False
        logging.info('Applying rule (\n%s\n) with certainty %f' % (self, cf))
        for conclusion in self.conclusions(instances):
            param, inst, op, val = conclusion
            logging.info('Concluding [%s] with certainty %f' %
                         (print_condition(conclusion), cf))
            update_cf(values, param, inst, val, cf)
        return True


# -----------------------------------------------------------------------------
# Shell
    
def parse_reply(param, reply):
    """
    Returns a list of (value, cf) pairs for the Parameter param from a text
    reply.  Expected a single value (with an implicit CF of true) or a list of
    value/cf pairs val1 cf1, val2 cf2, ....
    """
    if reply.find(',') >= 0:
        vals = []
        for pair in reply.split(','):
            val, cf = pair.strip().split(' ')
            vals.append((param.from_string(val), float(cf)))
        return vals
    return [(param.from_string(reply), CF.true)]

class Shell(object):
    
    """An expert system shell."""
    
    def __init__(self, read=raw_input, write=print):
        self.read = read
        self.write = write
        self.rules = {} # index rules under each param in the conclusions
        self.contexts = {} # indexed by name
        self.params = {} # indexed by name
        self.known = set() # (param, inst) pairs that have already been determined
        self.asked = set() # (param, inst) pairs that have already been asked
        self.known_values = {} # dict mapping (param, inst) to a list of (val, cf) pairs
        self.current_inst = None # the instance under consideration
        self.instances = {} # dict mapping ctx_name -> most recent instance of ctx
        self.current_rule = None # track the current rule for introspection
    
    def clear(self):
        """Clear per-problem state."""
        self.known.clear()
        self.asked.clear()
        self.known_values.clear()
        self.current_inst = None
        self.current_rule = None
        self.instances.clear()
    
    def define_rule(self, rule):
        for param, ctx, op, val in rule.raw_conclusions:
            self.rules.setdefault(param, []).append(rule)
    
    def get_rules(self, param):
        return self.rules.setdefault(param, [])
    
    def define_context(self, ctx):
        self.contexts[ctx.name] = ctx
        
    def instantiate(self, ctx_name):
        inst = self.contexts[ctx_name].instantiate()
        self.current_inst = inst
        self.instances[ctx_name] = inst
        return inst
    
    def define_param(self, param):
        self.params[param.name] = param
    
    def get_param(self, name):
        return self.params.setdefault(name, Parameter(name))
    
    def ask_values(self, param, inst):
        if (param, inst) in self.asked:
            return
        logging.debug('Getting user input for %s of %s' % (param, inst))
        self.asked.add((param, inst))
        while True:
            # TODO define prompts per Parameter
            resp = self.read('what is the %s of %s? ' % (param, inst))
            if resp == 'unknown':
                return False
            elif resp == 'help':
                # TODO
                pass
            elif resp == 'why':
                # TODO
                pass
            elif resp == 'rule':
                # TODO
                pass
            elif resp == '?':
                # TODO
                pass
            else:
                try:
                    for val, cf in parse_reply(self.get_param(param), resp):
                        update_cf(self.known_values, param, inst, val, cf)
                    return True
                except:
                    self.write('Invalid response. Type ? to see legal ones.')
    
    def _set_current_rule(self, rule):
        self.current_rule = rule
    
    def find_out(self, param, inst=None):
        """Use rules and user input to determine possible values for (param, inst)."""
        inst = inst or self.current_inst

        if (param, inst) in self.known:
            return True
        def rules():
            return use_rules(self.known_values, self.instances,
                             self.get_rules(param), self.find_out,
                             self._set_current_rule)

        logging.debug('Finding out %s of %s' % (param, inst))

        if self.get_param(param).ask_first:
            success = self.ask_values(param, inst) or rules()
        else:
            success = rules() or self.ask_values(param, inst)
        if success:
            self.known.add((param, inst))
        return success
    
    def execute(self, contexts):
        """
        Gather the goal data for each named context and report the findings.
        The system attempts to gather the initial data specified for the context
        before attempting to gather the goal data.
        """
        logging.info('Beginning data-gathering for %s' % ', '.join(contexts))
        self.clear()
        results = {}
        for name in contexts:
            ctx = self.contexts[name]
            self.instantiate(name)
            
            # gather initial data
            self._set_current_rule('initial')
            for param in ctx.initial_data:
                self.find_out(param)
            
            # find goal data
            self._set_current_rule('goal')
            for param in ctx.goals:
                self.find_out(param)
            
            # record findings
            if ctx.goals:
                result = {}
                for param in ctx.goals:
                    result[param] = get_vals(self.known_values, param, self.current_inst)
                results[self.current_inst] = result
            
        return results