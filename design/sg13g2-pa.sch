v {xschem version=3.4.7 file_version=1.2}
G {}
K {type=subcircuit
format="@name @pinlist @symname"
template="name=x1"}
V {}
S {}
E {}
T {sg13g2-pa  single-stage npn13G2 array PA core, bias and ideal match boundary} -600 -700 0 0 0.6 0.6 {}
T {Topology: DR 0003 (PROPOSED, not ratified): 14 x npn13G2 Nx=10 in parallel (140 Nx units), single common-emitter stage, no stack, 0.8 V nominal} -600 -650 0 0 0.35 0.35 {}
T {Passives are IDEAL (no loss, no self-resonance). Any Pout/PAE derived from this netlist is 'through ideal passives'. No inductor model is used (DR 0001 D-1 open)} -600 -620 0 0 0.35 0.35 {}
C {devices/ipin.sym} -600 -500 0 0 {name=p1 lab=RFIN}
C {devices/opin.sym} -600 -460 0 0 {name=p2 lab=RFOUT}
C {devices/iopin.sym} -600 -420 0 0 {name=p3 lab=VCC}
C {devices/iopin.sym} -600 -380 0 0 {name=p4 lab=GND}
T {PA CORE: 14 x npn13G2 Nx=10 (DR 0003)} -200 -540 0 0 0.5 0.5 {}
C {sg13g2_pr/npn13G2.sym} -100 0 0 0 {name=Q1 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} -80 -30 0 0 {name=lc1 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} -120 0 0 0 {name=lb1 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} -80 30 0 0 {name=le1 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -80 0 0 0 {name=ls1 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 20 0 0 0 {name=Q2 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 40 -30 0 0 {name=lc2 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 0 0 0 0 {name=lb2 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 40 30 0 0 {name=le2 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 40 0 0 0 {name=ls2 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 140 0 0 0 {name=Q3 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 160 -30 0 0 {name=lc3 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 120 0 0 0 {name=lb3 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 160 30 0 0 {name=le3 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 160 0 0 0 {name=ls3 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 260 0 0 0 {name=Q4 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 280 -30 0 0 {name=lc4 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 240 0 0 0 {name=lb4 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 280 30 0 0 {name=le4 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 280 0 0 0 {name=ls4 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 380 0 0 0 {name=Q5 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 400 -30 0 0 {name=lc5 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 360 0 0 0 {name=lb5 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 400 30 0 0 {name=le5 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 400 0 0 0 {name=ls5 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 500 0 0 0 {name=Q6 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 520 -30 0 0 {name=lc6 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 480 0 0 0 {name=lb6 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 520 30 0 0 {name=le6 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 520 0 0 0 {name=ls6 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 620 0 0 0 {name=Q7 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 640 -30 0 0 {name=lc7 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 600 0 0 0 {name=lb7 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 640 30 0 0 {name=le7 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 640 0 0 0 {name=ls7 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 740 0 0 0 {name=Q8 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 760 -30 0 0 {name=lc8 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 720 0 0 0 {name=lb8 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 760 30 0 0 {name=le8 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 760 0 0 0 {name=ls8 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 860 0 0 0 {name=Q9 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 880 -30 0 0 {name=lc9 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 840 0 0 0 {name=lb9 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 880 30 0 0 {name=le9 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 880 0 0 0 {name=ls9 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 980 0 0 0 {name=Q10 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 1000 -30 0 0 {name=lc10 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 960 0 0 0 {name=lb10 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 1000 30 0 0 {name=le10 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1000 0 0 0 {name=ls10 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 1100 0 0 0 {name=Q11 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 1120 -30 0 0 {name=lc11 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 1080 0 0 0 {name=lb11 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 1120 30 0 0 {name=le11 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1120 0 0 0 {name=ls11 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 1220 0 0 0 {name=Q12 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 1240 -30 0 0 {name=lc12 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 1200 0 0 0 {name=lb12 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 1240 30 0 0 {name=le12 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1240 0 0 0 {name=ls12 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 1340 0 0 0 {name=Q13 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 1360 -30 0 0 {name=lc13 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 1320 0 0 0 {name=lb13 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 1360 30 0 0 {name=le13 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1360 0 0 0 {name=ls13 sig_type=std_logic lab=GND}
C {sg13g2_pr/npn13G2.sym} 1460 0 0 0 {name=Q14 model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} 1480 -30 0 0 {name=lc14 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 1440 0 0 0 {name=lb14 sig_type=std_logic lab=VB}
C {devices/lab_pin.sym} 1480 30 0 0 {name=le14 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} 1480 0 0 0 {name=ls14 sig_type=std_logic lab=GND}
T {BIAS: ideal reference current into diode-connected npn13G2 (Nx=10), mirrored to the array (1:14); Rb isolates the reference from RF} -600 200 0 0 0.4 0.4 {}
C {devices/isource.sym} -540 330 0 0 {name=Iref value=1m}
C {devices/lab_pin.sym} -540 300 0 0 {name=li1 sig_type=std_logic lab=VCC}
C {devices/lab_pin.sym} -540 360 0 0 {name=li2 sig_type=std_logic lab=VREF}
C {sg13g2_pr/npn13G2.sym} -540 450 0 0 {name=Qref model=npn13G2 spiceprefix=X Nx=10}
C {devices/lab_pin.sym} -520 420 0 0 {name=lq1 sig_type=std_logic lab=VREF}
C {devices/lab_pin.sym} -560 450 0 0 {name=lq2 sig_type=std_logic lab=VREF}
C {devices/lab_pin.sym} -520 480 0 0 {name=lq3 sig_type=std_logic lab=GND}
C {devices/lab_pin.sym} -520 450 0 0 {name=lq4 sig_type=std_logic lab=GND}
C {devices/res.sym} -300 330 1 0 {name=Rb value=1k m=1}
C {devices/lab_pin.sym} -330 330 0 0 {name=lr1 sig_type=std_logic lab=VREF}
C {devices/lab_pin.sym} -270 330 0 0 {name=lr2 sig_type=std_logic lab=VB}
T {MATCHING / BIAS FEED: ideal passives only, off-chip match boundary at RFOUT. Values are non-tuned placeholders, not a match} 200 200 0 0 0.4 0.4 {}
C {devices/ind.sym} 260 330 0 0 {name=Lchoke value=100n m=1}
C {devices/lab_pin.sym} 260 300 0 0 {name=lm1 sig_type=std_logic lab=VCC}
C {devices/lab_pin.sym} 260 360 0 0 {name=lm2 sig_type=std_logic lab=COLL}
C {devices/capa.sym} 500 330 1 0 {name=Cblock value=100p m=1}
C {devices/lab_pin.sym} 470 330 0 0 {name=lm3 sig_type=std_logic lab=COLL}
C {devices/lab_pin.sym} 530 330 0 0 {name=lm4 sig_type=std_logic lab=RFOUT}
C {devices/capa.sym} 760 330 1 0 {name=Cin value=100p m=1}
C {devices/lab_pin.sym} 730 330 0 0 {name=lm5 sig_type=std_logic lab=RFIN}
C {devices/lab_pin.sym} 790 330 0 0 {name=lm6 sig_type=std_logic lab=VB}
