(define (problem blocksworld-train-00)
(:domain blocksworld-pick-place)
(:objects
    red green cyan - block
    table0 - table
    loc_a0 loc_a1 loc_a2 loc_a3 loc_b0 loc_b1 loc_b2 loc_b3 loc_c0 loc_c1 loc_c2 loc_c3 - location)
(:init
    ; stack 1
    (on red table0)
    (at-loc red loc_a1)
    (obstructed-above loc_a0)
    ; stack 2
    (on cyan table0)
    (at-loc cyan loc_b1)
    (obstructed-above loc_b0)
    ; stack 3
    (on green table0)
    (at-loc green loc_c1)
    (obstructed-above loc_c0)

    ; block attributes
    (wooden green)
    (plastic red) (plastic cyan)

    ; location relations
    (loc-above loc_a1 loc_a0) (loc-above loc_a2 loc_a1) (loc-above loc_a3 loc_a2)
    (loc-above loc_b1 loc_b0) (loc-above loc_b2 loc_b1) (loc-above loc_b3 loc_b2)
    (loc-above loc_c1 loc_c0) (loc-above loc_c2 loc_c1) (loc-above loc_c3 loc_c2)

    ; targets and table occupy the bottom row
    (at-loc table0 loc_a0) (at-loc table0 loc_b0) (at-loc table0 loc_c0)
)
(:goal
    (and
        (on red cyan)
        (on cyan green)
        (on green table0)
    )
)
)
