hms_endpoint_poll:
.LFB169:
	.loc 1 596 0
	.cfi_startproc
.LVL1575:
	push r2
.LCFI671:
	.cfi_def_cfa_offset 3
	.cfi_offset 2, -2
	push r3
.LCFI672:
	.cfi_def_cfa_offset 4
	.cfi_offset 3, -3
	push r4
.LCFI673:
	.cfi_def_cfa_offset 5
	.cfi_offset 4, -4
	push r5
.LCFI674:
	.cfi_def_cfa_offset 6
	.cfi_offset 5, -5
	push r6
.LCFI675:
	.cfi_def_cfa_offset 7
	.cfi_offset 6, -6
	push r7
.LCFI676:
	.cfi_def_cfa_offset 8
	.cfi_offset 7, -7
	push r8
.LCFI677:
	.cfi_def_cfa_offset 9
	.cfi_offset 8, -8
	push r9
.LCFI678:
	.cfi_def_cfa_offset 10
	.cfi_offset 9, -9
	push r10
.LCFI679:
	.cfi_def_cfa_offset 11
	.cfi_offset 10, -10
	push r11
.LCFI680:
	.cfi_def_cfa_offset 12
	.cfi_offset 11, -11
	push r12
.LCFI681:
	.cfi_def_cfa_offset 13
	.cfi_offset 12, -12
	push r13
.LCFI682:
	.cfi_def_cfa_offset 14
	.cfi_offset 13, -13
	push r14
.LCFI683:
	.cfi_def_cfa_offset 15
	.cfi_offset 14, -14
	push r15
.LCFI684:
	.cfi_def_cfa_offset 16
	.cfi_offset 15, -15
	push r16
.LCFI685:
	.cfi_def_cfa_offset 17
	.cfi_offset 16, -16
	push r17
.LCFI686:
	.cfi_def_cfa_offset 18
	.cfi_offset 17, -17
	push r28
.LCFI687:
	.cfi_def_cfa_offset 19
	.cfi_offset 28, -18
	push r29
.LCFI688:
	.cfi_def_cfa_offset 20
	.cfi_offset 29, -19
	in r28,__SP_L__
	in r29,__SP_H__
.LCFI689:
	.cfi_def_cfa_register 28
	subi r28,83
	sbc r29,__zero_reg__
.LCFI690:
	.cfi_def_cfa_offset 103
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
/* prologue: function */
/* frame size = 83 */
/* stack size = 101 */
.L__stack_usage = 101
	.loc 1 597 0
	sbiw r24,0
	breq .L1263
	movw r26,r24
	ld r30,X+
	ld r31,X
	or r30,r31
	breq .L1263
	movw r30,r24
	subi r30,-116
	sbci r31,-1
	ld r4,Z
	adiw r28,76-63
	std Y+63,r4
	sbiw r28,76-63
	cpse r4,__zero_reg__
	rjmp .L1263
	movw r2,r24
.LVL1576:
.LBB1035:
.LBB1036:
	.loc 1 598 0
	call update
.LVL1577:
	.loc 1 601 0
	movw r26,r2
	adiw r26,2
	ld r24,X+
	ld r25,X
	sbiw r24,0
	breq .L1265
	movw r30,r24
	ldd r18,Z+4
	cpi r18,lo8(2)
	brne .L1265
	.loc 1 602 0
	call hms_standing_poll
.LVL1578:
.L1263:
/* epilogue start */
.LBE1036:
.LBE1035:
	.loc 1 604 0
	subi r28,-83
	sbci r29,-1
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
	pop r29
	pop r28
	pop r17
	pop r16
	pop r15
	pop r14
	pop r13
	pop r12
	pop r11
	pop r10
	pop r9
	pop r8
	pop r7
	pop r6
	pop r5
	pop r4
	pop r3
	pop r2
	ret
.LVL1579:
.L1265:
.LBB1092:
.LBB1083:
.LBB1037:
.LBB1038:
	.loc 1 536 0
	movw r30,r2
	subi r30,-110
	sbci r31,-1
	ld r24,Z
	tst r24
	breq .L1263
	.loc 1 537 0
	movw r16,r2
.LVL1580:
	subi r16,-117
	sbci r17,-1
	adiw r28,77-62
	std Y+63,r17
	std Y+62,r16
	sbiw r28,77-62
.LVL1581:
	.loc 1 538 0
	subi r30,27
	sbci r31,-1
	ld r24,Z
.LBB1039:
.LBB1040:
	.loc 1 51 0
	ldi r25,lo8(-3)
	add r25,r24
.LBE1040:
.LBE1039:
	.loc 1 538 0
	cpi r25,lo8(4)
	brsh .L1267
	.loc 1 539 0
	adiw r30,4
	ld r24,Z
	tst r24
	breq .L1263
	sbiw r30,1
	ld r24,Z
.LBE1038:
.LBE1037:
.LBE1083:
.LBE1092:
	.loc 1 540 0
	ldi r17,lo8(4)
.LBB1093:
.LBB1084:
.LBB1075:
.LBB1067:
	.loc 1 539 0
	cpi r24,lo8(3)
	breq .L1263
.LVL1582:
.L1427:
.LBE1067:
.LBE1075:
.LBE1084:
.LBE1093:
	.loc 1 571 0
	std Y+55,r17
	rjmp .L1268
.LVL1583:
.L1267:
.LBB1094:
.LBB1085:
.LBB1076:
.LBB1068:
	.loc 1 541 0
	cpi r24,lo8(1)
	breq .+2
	rjmp .L1269
	.loc 1 542 0
	movw r30,r2
	subi r30,-108
	sbci r31,-1
	ld r24,Z
	cpi r24,lo8(2)
	breq .L1270
.LVL1584:
.L1272:
	.loc 1 543 0
	ldi r20,0
	ldi r22,lo8(6)
.L1429:
	.loc 1 545 0
	movw r24,r2
	call reject_queued
.LVL1585:
	rjmp .L1263
.LVL1586:
.L1270:
	.loc 1 542 0
	movw r30,r2
	subi r30,-109
	sbci r31,-1
	ld r24,Z
	tst r24
	breq .L1272
	.loc 1 543 0
	movw r24,r2
	subi r24,-119
	sbci r25,-1
	call get32
.LVL1587:
	.loc 1 542 0
	movw r26,r2
	adiw r26,28
	ld r16,X+
	ld r17,X+
	ld r18,X+
	ld r19,X
	sbiw r26,28+3
.LVL1588:
	cp r22,r16
	cpc r23,r17
	cpc r24,r18
	cpc r25,r19
	brne .L1272
	.loc 1 543 0
	movw r30,r2
	subi r30,-123
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbiw r30,51
	ld r18,Z
	ldd r19,Z+1
	cp r24,r18
	cpc r25,r19
	brne .L1272
	movw r24,r2
	call owns_resources
.LVL1589:
	tst r24
	breq .L1272
	.loc 1 544 0
	movw r30,r2
	ldd r4,Z+12
	ldd r5,Z+13
	ldd r6,Z+14
	ldd r7,Z+15
	ldd r8,Z+16
	ldd r9,Z+17
	ldd r31,Z+18
	std Y+55,r31
	movw r26,r2
	adiw r26,19
	ld r27,X
	std Y+63,r27
	movw r24,r2
	subi r24,87
	sbci r25,-1
	call get64
.LVL1590:
	movw r10,r18
	movw r12,r20
	movw r14,r22
.LVL1591:
	movw r16,r24
	movw r18,r4
	movw r20,r6
	movw r22,r8
	ldd r24,Y+55
	ldd r25,Y+63
	call __cmpdi2
	brsh .+2
	rjmp .L1263
	.loc 1 545 0
	movw r30,r2
	subi r30,79
	sbci r31,-1
	adiw r28,72-62
	std Y+63,r31
	std Y+62,r30
	sbiw r28,72-62
	movw r24,r30
	call get64
.LVL1592:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	movw r18,r4
	movw r20,r6
	movw r22,r8
	ldd r24,Y+55
	ldd r25,Y+63
	call __cmpdi2
	brlo .L1273
.L1276:
	ldi r20,0
	ldi r22,lo8(1)
	rjmp .L1429
.L1273:
	.loc 1 546 0
	movw r16,r2
	subi r16,59
	sbci r17,-1
	adiw r28,74-62
	std Y+63,r17
	std Y+62,r16
	sbiw r28,74-62
	movw r24,r16
	call get64
.LVL1593:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	movw r18,r4
	movw r20,r6
	movw r22,r8
	ldd r24,Y+55
	ldd r25,Y+63
	call __cmpdi2
	brlo .L1274
.L1277:
	ldi r20,0
	ldi r22,lo8(4)
	rjmp .L1429
.L1274:
	.loc 1 547 0
	adiw r28,77-62
	ldd r22,Y+62
	ldd r23,Y+63
	sbiw r28,77-62
	movw r24,r2
	call guard_call
.LVL1594:
	std Y+55,r24
.LVL1595:
	.loc 1 548 0
	ldi r20,0
	ldi r22,lo8(10)
	cpse r24,__zero_reg__
	rjmp .L1429
	.loc 1 549 0
	movw r24,r2
.LVL1596:
	call sample_clock
.LVL1597:
	.loc 1 550 0
	movw r30,r2
	subi r30,-83
	sbci r31,-2
	ld r24,Z
	cpi r24,lo8(1)
	breq .+2
	rjmp .L1263
	.loc 1 551 0
	subi r30,-25
	sbc r31,__zero_reg__
	ld r24,Z
	cpi r24,lo8(2)
	breq .+2
	rjmp .L1272
	adiw r30,1
	ld r24,Z
	tst r24
	brne .+2
	rjmp .L1272
	movw r24,r2
	call owns_resources
.LVL1598:
	tst r24
	brne .+2
	rjmp .L1272
	.loc 1 552 0
	movw r26,r2
	adiw r26,12
	ld r4,X
	sbiw r26,12
	adiw r26,13
	ld r5,X
	sbiw r26,13
	adiw r26,14
	ld r6,X
	sbiw r26,14
	adiw r26,15
	ld r7,X
	sbiw r26,15
	adiw r26,16
	ld r8,X
	sbiw r26,16
	adiw r26,17
	ld r9,X
	sbiw r26,17
	adiw r26,18
	ld r27,X
	std Y+63,r27
	movw r30,r2
	ldd r31,Z+19
	adiw r28,71-63
	std Y+63,r31
	sbiw r28,71-63
	adiw r28,72-62
	ldd r24,Y+62
	ldd r25,Y+63
	sbiw r28,72-62
	call get64
.LVL1599:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	movw r18,r4
	movw r20,r6
	movw r22,r8
	ldd r24,Y+63
	adiw r28,71-63
	ldd r25,Y+63
	sbiw r28,71-63
	call __cmpdi2
	brlo .+2
	rjmp .L1276
	.loc 1 553 0
	adiw r28,74-62
	ldd r24,Y+62
	ldd r25,Y+63
	sbiw r28,74-62
	call get64
.LVL1600:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	movw r18,r4
	movw r20,r6
	movw r22,r8
	ldd r24,Y+63
	adiw r28,71-63
	ldd r25,Y+63
	sbiw r28,71-63
	call __cmpdi2
	brlo .+2
	rjmp .L1277
	.loc 1 554 0
	movw r24,r2
	subi r24,63
	sbci r25,-1
	call get32
.LVL1601:
	movw r16,r22
	movw r18,r24
	mov r10,r22
	com r10
	mov r11,r17
	com r11
	mov r12,r24
	com r12
	mov r13,r19
	com r13
	movw r18,r4
	movw r20,r6
	movw r22,r8
	ldd r24,Y+63
	adiw r28,71-63
	ldd r25,Y+63
	sbiw r28,71-63
	clr r14
	dec r14
	clr r15
	dec r15
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	call __cmpdi2
	breq .L1278
	brlo .L1278
	ldi r20,0
	ldi r22,lo8(2)
	rjmp .L1429
.L1278:
	.loc 1 555 0
	movw r24,r2
	call revision
.LVL1602:
	tst r24
	brne .+2
	rjmp .L1263
	.loc 1 556 0
	ldi r24,lo8(2)
	movw r30,r2
	subi r30,-83
	sbci r31,-2
	st Z,r24
	ldi r24,lo8(1)
	adiw r30,5
	st Z,r24
	.loc 1 557 0
	movw r26,r2
	adiw r26,12
	ld r24,X
	sbiw r26,12
	sbiw r30,27
	st Z,r24
	adiw r26,13
	ld r24,X
	sbiw r26,13
	std Z+1,r24
	adiw r26,14
	ld r24,X
	sbiw r26,14
	std Z+2,r24
	adiw r26,15
	ld r24,X
	sbiw r26,15
	std Z+3,r24
	adiw r26,16
	ld r24,X
	sbiw r26,16
	std Z+4,r24
	adiw r26,17
	ld r24,X
	sbiw r26,17
	std Z+5,r24
	adiw r26,18
	ld r24,X
	sbiw r26,18
	std Z+6,r24
	adiw r26,19
	ld r24,X
	std Z+7,r24
.LVL1603:
.L1268:
	.loc 1 575 0
	movw r24,r2
	subi r24,79
	sbci r25,-1
	call get64
.LVL1604:
	std Y+39,r18
	std Y+40,r19
	std Y+41,r20
	std Y+42,r21
	std Y+43,r22
	std Y+44,r23
	std Y+45,r24
	std Y+46,r25
	.loc 1 576 0
	movw r24,r2
	subi r24,71
	sbci r25,-1
	call get64
.LVL1605:
	mov r5,r18
	mov r10,r19
	mov r11,r20
	mov r12,r21
	mov r13,r22
	mov r14,r23
	mov r15,r24
	mov r16,r25
	std Y+47,r18
	std Y+48,r19
	std Y+49,r20
	std Y+50,r21
	std Y+51,r22
	std Y+52,r23
	std Y+53,r24
	std Y+54,r25
	.loc 1 577 0
	movw r24,r2
	subi r24,59
	sbci r25,-1
	call get64
.LVL1606:
	movw r6,r18
	movw r8,r20
	mov r27,r22
	mov r26,r23
	mov r31,r24
	mov r30,r25
	mov r18,r5
	mov r19,r10
	mov r20,r11
	mov r21,r12
	mov r22,r13
	mov r23,r14
	mov r24,r15
	mov r25,r16
	movw r10,r6
	movw r12,r8
	mov r14,r27
	mov r15,r26
	mov r16,r31
	mov r17,r30
	call __cmpdi2
	breq .L1289
	brlo .L1289
	std Y+47,r6
	std Y+48,r7
	std Y+49,r8
	std Y+50,r9
	std Y+51,r27
	std Y+52,r26
	std Y+53,r31
	std Y+54,r30
.L1289:
	.loc 1 578 0
	movw r30,r2
	subi r30,-61
	sbci r31,-2
	ld r8,Z
	ldd r9,Z+1
	ldd r7,Z+2
	ldd r6,Z+3
	ldd r5,Z+4
	ldd r4,Z+5
	ldd r19,Z+6
	adiw r28,71-63
	std Y+63,r19
	sbiw r28,71-63
	ldd r20,Z+7
	adiw r28,72-63
	std Y+63,r20
	sbiw r28,72-63
	movw r18,r8
	mov r20,r7
	mov r21,r6
	mov r22,r5
	mov r23,r4
	adiw r28,71-63
	ldd r24,Y+63
	sbiw r28,71-63
	adiw r28,72-63
	ldd r25,Y+63
	sbiw r28,72-63
	ldi r26,lo8(-1)
	call __cmpdi2_s8
	brne .+2
	rjmp .L1290
	.loc 1 579 0
	movw r24,r2
	subi r24,63
	sbci r25,-1
	call get32
.LVL1607:
	movw r14,r22
	movw r16,r24
	ldi r18,0
	ldi r19,0
	movw r20,r18
	std Y+63,r22
	adiw r28,64-63
	std Y+63,r15
	sbiw r28,64-63
	adiw r28,65-63
	std Y+63,r24
	sbiw r28,65-63
	adiw r28,66-63
	std Y+63,r17
	sbiw r28,66-63
	adiw r28,67-63
	std Y+63,r18
	sbiw r28,67-63
	adiw r28,68-63
	std Y+63,r19
	sbiw r28,68-63
	adiw r28,69-63
	std Y+63,r20
	sbiw r28,69-63
	adiw r28,70-63
	std Y+63,r21
	sbiw r28,70-63
	mov r10,r22
	com r10
	mov r11,r15
	com r11
	mov r12,r24
	com r12
	mov r13,r17
	com r13
	.loc 1 578 0
	movw r18,r8
	mov r20,r7
	mov r21,r6
	mov r22,r5
	mov r23,r4
	adiw r28,71-63
	ldd r24,Y+63
	sbiw r28,71-63
	adiw r28,72-63
	ldd r25,Y+63
	sbiw r28,72-63
	clr r14
	dec r14
	clr r15
	dec r15
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	call __cmpdi2
	breq .+2
	brsh .L1290
	.loc 1 580 0
	ldd r10,Y+63
	adiw r28,64-63
	ldd r11,Y+63
	sbiw r28,64-63
	adiw r28,65-63
	ldd r12,Y+63
	sbiw r28,65-63
	adiw r28,66-63
	ldd r13,Y+63
	sbiw r28,66-63
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __adddi3
	movw r6,r18
	movw r8,r20
	.loc 1 579 0
	ldd r10,Y+47
	ldd r11,Y+48
	ldd r12,Y+49
	ldd r13,Y+50
	ldd r14,Y+51
	ldd r15,Y+52
	ldd r16,Y+53
	ldd r17,Y+54
	call __cmpdi2
	brsh .L1290
	.loc 1 581 0
	std Y+47,r18
	std Y+48,r7
	std Y+49,r20
	std Y+50,r9
	std Y+51,r22
	std Y+52,r23
	std Y+53,r24
	std Y+54,r25
.L1290:
	.loc 1 582 0
	movw r26,r28
	adiw r26,1
	ldi r24,lo8(38)
	movw r30,r26
	0:
	st Z+,__zero_reg__
	dec r24
	brne 0b
	.loc 1 583 0
	movw r4,r2
	ldi r31,116
	add r4,r31
	adc r5,__zero_reg__
	ldi r24,lo8(1)
	movw r30,r4
	st Z,r24
	.loc 1 584 0
	movw r30,r2
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	adiw r28,63-62
	std Y+63,r31
	std Y+62,r30
	sbiw r28,63-62
	ldd r6,Z+10
	ldd r7,Z+11
	movw r30,r2
	ldd r8,Z+12
	ldd r9,Z+13
	ldd r10,Z+14
	ldd r11,Z+15
	ldd r12,Z+16
	ldd r13,Z+17
	ldd r14,Z+18
	ldd r15,Z+19
	movw r24,r2
	subi r24,92
	sbci r25,-1
	movw r30,r24
	ld r16,Z
.LVL1608:
.LBB1041:
.LBB1042:
	.loc 1 267 0
	sbiw r24,1
	movw r30,r24
	ld r24,Z
.LVL1609:
.L1291:
.LBB1043:
.LBB1044:
	.loc 1 42 0
	cpse r24,__zero_reg__
	rjmp .L1292
.LVL1610:
.LBE1044:
.LBE1043:
	.loc 1 267 0
	adiw r28,76-63
	ldd r17,Y+63
	sbiw r28,76-63
	mov r18,r17
	ldi r19,0
	subi r18,-22
	sbci r19,-1
	lsl r18
	rol r19
	lsl r18
	rol r19
	adiw r28,77-62
	ldd r20,Y+62
	ldd r21,Y+63
	sbiw r28,77-62
	add r18,r20
	adc r19,r21
.LBE1042:
.LBE1041:
	.loc 1 584 0
	movw r24,r2
	subi r24,95
	sbci r25,-1
	movw r30,r24
	ld r20,Z
	ldd r21,Z+1
	eor r21,r20
	eor r20,r21
	eor r21,r20
	push r27
	push r26
	movw r24,r28
	adiw r24,39
	push r25
	push r24
	ldd r22,Y+55
	adiw r28,63-62
	ldd r26,Y+62
	ldd r27,Y+63
	sbiw r28,63-62
	ld r24,X+
	ld r25,X
	movw r30,r6
	icall
.LVL1611:
	.loc 1 585 0
	movw r26,r4
	st X,__zero_reg__
	.loc 1 586 0
	movw r24,r2
	call sample_clock
.LVL1612:
	.loc 1 587 0
	ldi r22,lo8(1)
	ldd r4,Y+55
	cpse r4,__zero_reg__
	ldi r22,0
.L1293:
	movw r24,r2
	call cutoff_reason
.LVL1613:
	.loc 1 588 0
	pop __tmp_reg__
	pop __tmp_reg__
	pop __tmp_reg__
	pop __tmp_reg__
	tst r24
	brne .+2
	rjmp .L1294
	ldd r25,Y+1
	cpi r25,lo8(3)
	breq .L1295
	ldd r5,Y+55
	cpse r5,__zero_reg__
	rjmp .L1296
.L1295:
	.loc 1 590 0
	mov r22,r24
	movw r24,r2
.LVL1614:
	call unknown_report
.LVL1615:
	rjmp .L1263
.LVL1616:
.L1269:
	.loc 1 559 0
	movw r8,r2
	ldi r27,111
	add r8,r27
	adc r9,__zero_reg__
	movw r30,r8
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1280
	.loc 1 560 0
	sbiw r30,3
	ld r24,Z
	cpi r24,lo8(4)
	brne .L1281
	ldi r24,lo8(7)
.LVL1617:
.L1424:
	.loc 1 562 0
	movw r26,r8
.L1425:
	st X,r24
.L1280:
	.loc 1 568 0
	movw r24,r2
	call sample_clock
.LVL1618:
	.loc 1 569 0
	ldi r22,0
	movw r24,r2
	call cutoff_reason
.LVL1619:
	movw r30,r2
	subi r30,-111
	sbci r31,-1
	.loc 1 570 0
	cpse r24,__zero_reg__
	st Z,r24
.L1288:
	.loc 1 571 0
	ld r24,Z
.LVL1620:
	cpse r24,__zero_reg__
	rjmp .L1334
	movw r30,r2
	subi r30,-83
	sbci r31,-2
	ld r24,Z
	cpi r24,lo8(7)
	brne .+2
	rjmp .L1335
	.loc 1 572 0
	adiw r30,1
	ld r24,Z
	subi r24,lo8(-(-1))
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L1336
.LBE1068:
.LBE1076:
.LBE1085:
.LBE1094:
	ldi r31,lo8(2)
	std Y+55,r31
	rjmp .L1268
.LVL1621:
.L1281:
.LBB1095:
.LBB1086:
.LBB1077:
.LBB1069:
	.loc 1 561 0
	movw r30,r2
	subi r30,-109
	sbci r31,-1
	ld r24,Z
	tst r24
	breq .L1282
	movw r24,r2
	subi r24,-119
	sbci r25,-1
	call get32
.LVL1622:
	movw r30,r2
	ldd r16,Z+28
	ldd r17,Z+29
	ldd r18,Z+30
	ldd r19,Z+31
.LVL1623:
	cp r22,r16
	cpc r23,r17
	cpc r24,r18
	cpc r25,r19
	brne .L1282
	subi r30,-123
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	.loc 1 562 0
	sbiw r30,51
	.loc 1 561 0
	ld r18,Z
	ldd r19,Z+1
	cp r24,r18
	cpc r25,r19
	brne .L1282
	.loc 1 562 0
	movw r24,r2
	call owns_resources
.LVL1624:
	cpse r24,__zero_reg__
	rjmp .L1283
.L1282:
	ldi r24,lo8(6)
	rjmp .L1424
.L1283:
	.loc 1 563 0
	movw r30,r2
	ldd r5,Z+12
	ldd r4,Z+13
	ldd r6,Z+14
	std Y+55,r6
	ldd r7,Z+15
	std Y+63,r7
	ldd r6,Z+16
	adiw r28,71-63
	std Y+63,r6
	sbiw r28,71-63
	ldd r7,Z+17
	adiw r28,72-63
	std Y+63,r7
	sbiw r28,72-63
	ldd r6,Z+18
	ldd r7,Z+19
	movw r24,r2
	subi r24,59
	sbci r25,-1
	call get64
.LVL1625:
	movw r10,r18
	movw r12,r20
	movw r14,r22
.LVL1626:
	movw r16,r24
	mov r18,r5
	mov r19,r4
	ldd r20,Y+55
	ldd r21,Y+63
	adiw r28,71-63
	ldd r22,Y+63
	sbiw r28,71-63
	adiw r28,72-63
	ldd r23,Y+63
	sbiw r28,72-63
	movw r24,r6
	call __cmpdi2
	brlo .L1284
	ldi r24,lo8(4)
	rjmp .L1424
.L1284:
	.loc 1 564 0
	movw r24,r2
	subi r24,71
	sbci r25,-1
	call get64
.LVL1627:
	movw r10,r18
	movw r12,r20
	movw r14,r22
	movw r16,r24
	mov r18,r5
	mov r19,r4
	ldd r20,Y+55
	ldd r21,Y+63
	adiw r28,71-63
	ldd r22,Y+63
	sbiw r28,71-63
	adiw r28,72-63
	ldd r23,Y+63
	sbiw r28,72-63
	movw r24,r6
	call __cmpdi2
	brlo .L1285
	ldi r24,lo8(3)
	movw r30,r8
.L1426:
	.loc 1 566 0
	st Z,r24
	rjmp .L1280
.L1285:
	.loc 1 565 0
	movw r30,r2
	subi r30,-61
	sbci r31,-2
	ld r8,Z
	adiw r28,74-63
	std Y+63,r8
	sbiw r28,74-63
	ldd r9,Z+1
	adiw r28,79-63
	std Y+63,r9
	sbiw r28,79-63
	ldd r8,Z+2
	ldd r9,Z+3
	ldd r27,Z+4
	ldd r26,Z+5
	ldd r10,Z+6
	adiw r28,80-63
	std Y+63,r10
	sbiw r28,80-63
	ldd r11,Z+7
	adiw r28,83-63
	std Y+63,r11
	sbiw r28,83-63
	ldd r20,Y+55
	ldd r21,Y+63
	adiw r28,71-63
	ldd r22,Y+63
	sbiw r28,71-63
	adiw r28,72-63
	ldd r23,Y+63
	sbiw r28,72-63
	movw r24,r6
	adiw r28,74-63
	ldd r10,Y+63
	sbiw r28,74-63
	adiw r28,79-63
	ldd r11,Y+63
	sbiw r28,79-63
	movw r12,r8
	mov r14,r27
	mov r15,r26
	adiw r28,80-63
	ldd r16,Y+63
	sbiw r28,80-63
	adiw r28,83-63
	ldd r17,Y+63
	sbiw r28,83-63
	subi r30,-50
	sbc r31,__zero_reg__
	adiw r28,81-62
	std Y+63,r31
	std Y+62,r30
	sbiw r28,81-62
	call __cmpdi2
	brlo .L1286
	call __subdi3
	mov r17,r18
	std Y+63,r19
	adiw r28,71-63
	std Y+63,r20
	sbiw r28,71-63
	mov r12,r21
	mov r13,r22
	mov r14,r23
	mov r15,r24
	mov r16,r25
	movw r24,r2
	subi r24,63
	sbci r25,-1
	call get32
.LVL1628:
	movw r4,r22
	movw r6,r24
	mov r8,__zero_reg__
	mov r9,__zero_reg__
	movw r10,r8
	std Y+55,r22
	std Y+56,r5
	std Y+57,r24
	std Y+58,r7
	std Y+59,r8
	std Y+60,r9
	std Y+61,r10
	std Y+62,r11
	mov r18,r17
	ldd r19,Y+63
	adiw r28,71-63
	ldd r20,Y+63
	sbiw r28,71-63
	mov r21,r12
	mov r22,r13
	mov r23,r14
	mov r24,r15
	mov r25,r16
	movw r10,r4
	movw r12,r6
	mov r14,__zero_reg__
	mov r15,__zero_reg__
	ldi r16,0
	ldi r17,0
	call __cmpdi2
	brlo .L1286
	ldi r24,lo8(2)
	adiw r28,81-62
	ldd r26,Y+62
	ldd r27,Y+63
	sbiw r28,81-62
	rjmp .L1425
.L1286:
	.loc 1 566 0
	adiw r28,77-62
	ldd r22,Y+62
	ldd r23,Y+63
	sbiw r28,77-62
	movw r24,r2
	call guard_call
.LVL1629:
	tst r24
	brne .+2
	rjmp .L1280
	ldi r24,lo8(10)
	adiw r28,81-62
	ldd r30,Y+62
	ldd r31,Y+63
	sbiw r28,81-62
	rjmp .L1426
.L1334:
.LBE1069:
.LBE1077:
.LBE1086:
.LBE1095:
	.loc 1 571 0
	ldi r16,lo8(3)
	std Y+55,r16
	rjmp .L1268
.L1335:
	ldi r17,lo8(3)
	rjmp .L1427
.L1336:
	.loc 1 573 0
	ldi r18,lo8(1)
	std Y+55,r18
	rjmp .L1268
.LVL1630:
.L1292:
.LBB1096:
.LBB1087:
.LBB1078:
.LBB1070:
.LBB1048:
.LBB1047:
.LBB1046:
.LBB1045:
	.loc 1 42 0
	mov r25,r24
	andi r25,lo8(1)
	adiw r28,76-63
	ldd r31,Y+63
	sbiw r28,76-63
	add r31,r25
	adiw r28,76-63
	std Y+63,r31
	sbiw r28,76-63
.LVL1631:
	lsr r24
.LVL1632:
	rjmp .L1291
.LVL1633:
.L1296:
.LBE1045:
.LBE1046:
.LBE1047:
.LBE1048:
	.loc 1 592 0
	movw r30,r2
	subi r30,-83
	sbci r31,-2
.LBB1049:
.LBB1050:
	.loc 1 51 0
	ld r25,Z
	subi r25,lo8(-(-3))
.LBE1050:
.LBE1049:
	.loc 1 592 0
	cpi r25,lo8(4)
	brlo .L1294
	subi r30,-28
	sbc r31,__zero_reg__
	st Z,r24
.L1294:
.LVL1634:
.LBB1051:
.LBB1052:
	.loc 1 456 0
	ldd r20,Y+6
	cpi r20,lo8(33)
	brsh .L1297
	ldd r24,Y+3
.LVL1635:
	cpi r24,lo8(6)
	brsh .L1297
	ldd r22,Y+4
	cpi r22,lo8(4)
	brsh .L1297
	.loc 1 457 0
	ldd r25,Y+2
	.loc 1 456 0
	tst r25
	breq .L1298
	.loc 1 457 0
	ldi r18,lo8(-2)
	add r18,r25
	cpi r18,lo8(2)
	brsh .L1297
.L1298:
	.loc 1 458 0
	ldd r19,Y+5
	movw r16,r2
	subi r16,-87
	sbci r17,-2
	movw r26,r16
	ld r18,X
	com r18
	and r18,r19
	.loc 1 457 0
	brne .L1297
	.loc 1 458 0
	cpse r24,__zero_reg__
	rjmp .L1299
	.loc 1 459 0
	tst r20
	breq .L1300
.L1297:
	.loc 1 463 0
	movw r24,r2
	call bad_report
.LVL1636:
	rjmp .L1263
.L1299:
	.loc 1 459 0
	tst r20
	breq .L1300
	.loc 1 460 0
	movw r30,r2
	subi r30,-114
	sbci r31,-1
	ld r18,Z
	cpse r20,r18
	rjmp .L1297
.L1300:
	.loc 1 461 0
	movw r30,r2
	subi r30,-115
	sbci r31,-1
	.loc 1 460 0
	ld r18,Z
	tst r18
	breq .L1301
	.loc 1 462 0
	ldi r18,lo8(-3)
	add r18,r24
	.loc 1 461 0
	cpi r18,lo8(2)
	brlo .L1297
.L1302:
	.loc 1 464 0
	cpi r22,lo8(1)
	brne .L1303
	.loc 1 465 0
	movw r30,r2
	subi r30,-74
	sbci r31,-1
	ld r18,Z
	.loc 1 464 0
	sbrs r18,2
	rjmp .L1297
	.loc 1 466 0
	ldi r18,lo8(-3)
	add r18,r24
	.loc 1 465 0
	cpi r18,lo8(2)
	brsh .L1297
.L1303:
	.loc 1 455 0
	movw r14,r2
	ldi r27,-83
	sub r14,r27
	ldi r27,-2
	sbc r15,r27
.LBB1053:
.LBB1054:
	.loc 1 51 0
	movw r30,r14
	ld r21,Z
	subi r21,lo8(-(-3))
.LBE1054:
.LBE1053:
	.loc 1 467 0
	ldd r18,Y+1
	tst r18
	brne .+2
	rjmp .L1304
	cpi r21,lo8(4)
	brlo .L1297
	.loc 1 468 0
	ldi r21,lo8(-3)
	add r21,r18
	cpi r21,lo8(3)
	brlo .L1305
	cpi r18,lo8(7)
	brne .L1297
.L1306:
	.loc 1 474 0
	cpse r19,__zero_reg__
	rjmp .L1329
	rjmp .L1421
.L1301:
	.loc 1 463 0
	cpi r24,lo8(5)
	brne .L1302
	rjmp .L1297
.L1305:
	.loc 1 469 0
	cpi r18,lo8(3)
	brne .L1307
	.loc 1 470 0
	movw r30,r2
	subi r30,-111
	sbci r31,-1
	.loc 1 469 0
	ld r21,Z
	cpse r21,__zero_reg__
	rjmp .L1297
	.loc 1 470 0
	adiw r30,3
	ld r21,Z
	cpse r20,r21
	rjmp .L1297
	.loc 1 471 0
	sbiw r30,2
	ld r20,Z
	ldi r21,0
	rjmp 2f
	1:
	asr r21
	ror r20
	2:
	dec r24
	brpl 1b
	.loc 1 470 0
	sbrs r20,0
	rjmp .L1297
	.loc 1 472 0
	adiw r30,53
	.loc 1 471 0
	ld r24,Z
	tst r24
	breq .L1306
	.loc 1 472 0
	cpi r22,lo8(1)
	breq .+2
	rjmp .L1297
	rjmp .L1306
.L1307:
	.loc 1 473 0
	cpi r18,lo8(5)
	brne .L1306
	movw r30,r2
	subi r30,-84
	sbci r31,-2
	ld r24,Z
	subi r24,lo8(-(-1))
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L1297
	rjmp .L1306
.L1333:
	.loc 1 474 0
	cpi r21,lo8(4)
	brsh .+2
	rjmp .L1309
.L1329:
.LBB1055:
.LBB1056:
	.loc 1 51 0
	ldi r24,lo8(-3)
	add r24,r18
.LBE1056:
.LBE1055:
	.loc 1 474 0
	cpi r24,lo8(4)
	brlo .+2
	rjmp .L1297
.L1421:
	.loc 1 476 0
	tst r25
	breq .L1312
.L1331:
	movw r30,r2
	subi r30,-84
	sbci r31,-2
	ld r24,Z
	ldi r20,lo8(-1)
	add r20,r24
	cpi r20,lo8(3)
	brlo .+2
	rjmp .L1297
	.loc 1 477 0
	cpse r18,__zero_reg__
	rjmp .L1312
	cpse r19,__zero_reg__
	rjmp .L1312
	tst r25
	brne .+2
	rjmp .L1263
	.loc 1 478 0
	cp r25,r24
	brne .+2
	rjmp .L1263
.L1312:
.LVL1637:
	.loc 1 479 0
	movw r24,r2
	call revision
.LVL1638:
	tst r24
	brne .+2
	rjmp .L1263
	.loc 1 480 0
	ldd r24,Y+2
	tst r24
	breq .L1313
	movw r30,r2
	subi r30,-84
	sbci r31,-2
	st Z,r24
.L1313:
	.loc 1 481 0
	ldd r11,Y+1
	movw r18,r2
	subi r18,-86
	sbci r19,-2
	movw r12,r18
	tst r11
	brne .+2
	rjmp .L1315
	.loc 1 482 0
	movw r26,r14
	st X,r11
	ldd r24,Y+3
	movw r30,r2
	subi r30,-85
	sbci r31,-2
	st Z,r24
	.loc 1 483 0
	ldd r24,Y+4
	movw r30,r18
	st Z,r24
	ldd r20,Y+6
	adiw r30,3
	st Z,r20
	.loc 1 484 0
	ldi r21,0
	movw r22,r28
	subi r22,-7
	sbci r23,-1
	movw r24,r2
	subi r24,-90
	sbci r25,-2
	call memcpy
.LVL1639:
.LBB1057:
.LBB1058:
	.loc 1 51 0
	ldi r25,lo8(-3)
	add r25,r11
.LVL1640:
.LBE1058:
.LBE1057:
	.loc 1 485 0
	cpi r25,lo8(4)
	brsh .L1316
	.loc 1 486 0
	movw r30,r2
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	sbrs r24,4
	rjmp .L1337
	movw r30,r2
	ldd r26,Z+12
	ldd r23,Z+13
	ldd r22,Z+14
	ldd r21,Z+15
	ldd r20,Z+16
	ldd r19,Z+17
	ldd r18,Z+18
	ldd r24,Z+19
.L1317:
	movw r30,r2
	subi r30,-69
	sbci r31,-2
	st Z,r26
	std Z+1,r23
	std Z+2,r22
	std Z+3,r21
	std Z+4,r20
	std Z+5,r19
	std Z+6,r18
	std Z+7,r24
.L1316:
	.loc 1 487 0
	movw r30,r2
	subi r30,-111
	sbci r31,-1
	ld r24,Z
	tst r24
	breq .L1318
	movw r26,r2
	subi r26,-81
	sbci r27,-2
	mov r18,r24
	ldi r19,0
	st X+,r18
	st X,r19
.L1318:
	.loc 1 488 0
	ldi r19,lo8(5)
	mov r4,r19
	cpse r11,r4
	rjmp .L1319
	.loc 1 489 0
	ldi r24,lo8(4)
	movw r30,r2
	subi r30,-84
	sbci r31,-2
	st Z,r24
	.loc 1 490 0
	subi r30,10
	sbci r31,1
	ld r24,Z
	sbrs r24,4
	rjmp .L1338
.LBE1052:
.LBE1051:
.LBE1070:
.LBE1078:
.LBE1087:
.LBE1096:
	ldi r24,lo8(5)
	ldi r25,0
.L1320:
.LBB1097:
.LBB1088:
.LBB1079:
.LBB1071:
.LBB1063:
.LBB1059:
	movw r30,r2
	subi r30,-81
	sbci r31,-2
	std Z+1,r25
	st Z,r24
.L1321:
	.loc 1 496 0
	movw r30,r2
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	sbrc r24,4
	rjmp .L1315
	.loc 1 497 0
	ldi r24,lo8(7)
	ldi r25,0
	subi r30,-7
	sbci r31,-2
	std Z+1,r25
	st Z,r24
	rjmp .L1315
.L1337:
.LBE1059:
.LBE1063:
.LBE1071:
.LBE1079:
.LBE1088:
.LBE1097:
	.loc 1 486 0
	ldi r26,lo8(-1)
	ldi r23,lo8(-1)
	ldi r22,lo8(-1)
	ldi r21,lo8(-1)
	ldi r20,lo8(-1)
	ldi r19,lo8(-1)
	ldi r18,lo8(-1)
	ldi r24,lo8(-1)
	rjmp .L1317
.L1338:
	.loc 1 490 0
	ldi r24,lo8(7)
	ldi r25,0
	rjmp .L1320
.L1319:
.LBB1098:
.LBB1089:
.LBB1080:
.LBB1072:
.LBB1064:
.LBB1060:
	.loc 1 492 0
	ldi r18,lo8(7)
	mov r5,r18
	cpse r11,r5
	rjmp .L1322
	.loc 1 493 0
	movw r26,r2
	subi r26,-74
	sbci r27,-1
	ld r25,X
	subi r26,-7
	sbci r27,-2
	sbrc r25,4
	rjmp .L1323
	st Z,r11
	ldi r24,lo8(7)
	ldi r25,0
.L1428:
	.loc 1 494 0
	st X+,r24
	st X,r25
.L1315:
	.loc 1 499 0
	movw r26,r12
	ld r24,X
	cpi r24,lo8(3)
	brne .L1326
	.loc 1 502 0
	movw r30,r2
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	sbrs r24,4
	rjmp .L1339
.LBE1060:
.LBE1064:
.LBE1072:
.LBE1080:
.LBE1089:
.LBE1098:
	ldi r24,lo8(8)
	ldi r25,0
.L1327:
.LBB1099:
.LBB1090:
.LBB1081:
.LBB1073:
.LBB1065:
.LBB1061:
	movw r30,r2
	subi r30,-81
	sbci r31,-2
	std Z+1,r25
	st Z,r24
	.loc 1 503 0
	ldi r22,lo8(8)
	movw r24,r2
	call fault
.LVL1641:
.L1328:
	.loc 1 505 0
	movw r24,r2
	call drain_state
.LVL1642:
	rjmp .L1263
.LVL1643:
.L1323:
	.loc 1 494 0
	cpse r24,__zero_reg__
	rjmp .L1324
	ldi r24,lo8(8)
	st Z,r24
.L1324:
	ldi r24,lo8(9)
	ldi r25,0
	rjmp .L1428
.L1322:
	.loc 1 496 0
	cpi r25,lo8(4)
	brsh .L1315
	rjmp .L1321
.L1339:
.LBE1061:
.LBE1065:
.LBE1073:
.LBE1081:
.LBE1090:
.LBE1099:
	.loc 1 502 0
	ldi r24,lo8(7)
	ldi r25,0
	rjmp .L1327
.L1326:
.LBB1100:
.LBB1091:
.LBB1082:
.LBB1074:
.LBB1066:
.LBB1062:
	.loc 1 504 0
	ldd r24,Y+5
	com r24
	movw r30,r16
	ld r25,Z
	and r24,r25
	st Z,r24
	rjmp .L1328
.LVL1644:
.L1304:
	.loc 1 474 0
	cpse r19,__zero_reg__
	rjmp .L1333
.L1309:
	.loc 1 475 0
	cpse r20,__zero_reg__
	rjmp .L1297
	cpse r24,__zero_reg__
	rjmp .L1297
	cpse r22,__zero_reg__
	rjmp .L1297
	.loc 1 476 0
	cpse r25,__zero_reg__
	rjmp .L1331
	.loc 1 477 0
	cpse r19,__zero_reg__
	rjmp .L1312
	rjmp .L1263
.LBE1062:
.LBE1066:
.LBE1074:
.LBE1082:
.LBE1091:
.LBE1100:
	.cfi_endproc
.LFE169:
	.size	hms_endpoint_poll, .-hms_endpoint_poll
