import logging
from paip import logic

def main():
    x = logic.Var('x')
    y = logic.Var('y')
    z = logic.Var('z')
    a = logic.Var('a')
    nil = logic.Atom('nil')
    more = logic.Var('more')
    zero = logic.Atom('0')

    length_nil = logic.Fact(logic.Relation('length', (nil, zero)))
    length_one = logic.Rule(
        logic.Relation('length',
                       (logic.Relation('pair', (x, more)),
                        logic.Relation('+1', [a]))),
        [logic.Relation('length', (more, a))])

    db = logic.Database()
    db.store(length_nil)
    db.store(length_one)

    print 'Database:'
    print db
    print

    list = logic.Relation(
        'pair', (x, logic.Relation(
                'pair', (y, logic.Relation(
                        'pair', (z, nil))))))
    
    query = logic.Relation('length', (list, a))
    print 'Query:', query
    print
    
    logic.prolog_prove([query], db)