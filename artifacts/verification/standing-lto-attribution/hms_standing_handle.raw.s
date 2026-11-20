hms_standing_handle:
.LFB160:
	.loc 11 436 0
	.cfi_startproc
.LVL1257:
	push r2
.LCFI651:
	.cfi_def_cfa_offset 3
	.cfi_offset 2, -2
	push r3
.LCFI652:
	.cfi_def_cfa_offset 4
	.cfi_offset 3, -3
	push r4
.LCFI653:
	.cfi_def_cfa_offset 5
	.cfi_offset 4, -4
	push r5
.LCFI654:
	.cfi_def_cfa_offset 6
	.cfi_offset 5, -5
	push r6
.LCFI655:
	.cfi_def_cfa_offset 7
	.cfi_offset 6, -6
	push r7
.LCFI656:
	.cfi_def_cfa_offset 8
	.cfi_offset 7, -7
	push r8
.LCFI657:
	.cfi_def_cfa_offset 9
	.cfi_offset 8, -8
	push r9
.LCFI658:
	.cfi_def_cfa_offset 10
	.cfi_offset 9, -9
	push r10
.LCFI659:
	.cfi_def_cfa_offset 11
	.cfi_offset 10, -10
	push r11
.LCFI660:
	.cfi_def_cfa_offset 12
	.cfi_offset 11, -11
	push r12
.LCFI661:
	.cfi_def_cfa_offset 13
	.cfi_offset 12, -12
	push r13
.LCFI662:
	.cfi_def_cfa_offset 14
	.cfi_offset 13, -13
	push r14
.LCFI663:
	.cfi_def_cfa_offset 15
	.cfi_offset 14, -14
	push r15
.LCFI664:
	.cfi_def_cfa_offset 16
	.cfi_offset 15, -15
	push r16
.LCFI665:
	.cfi_def_cfa_offset 17
	.cfi_offset 16, -16
	push r17
.LCFI666:
	.cfi_def_cfa_offset 18
	.cfi_offset 17, -17
	push r28
.LCFI667:
	.cfi_def_cfa_offset 19
	.cfi_offset 28, -18
	push r29
.LCFI668:
	.cfi_def_cfa_offset 20
	.cfi_offset 29, -19
	in r28,__SP_L__
	in r29,__SP_H__
.LCFI669:
	.cfi_def_cfa_register 28
	sbiw r28,23
.LCFI670:
	.cfi_def_cfa_offset 43
	in __tmp_reg__,__SREG__
	cli
	out __SP_H__,r29
	out __SREG__,__tmp_reg__
	out __SP_L__,r28
/* prologue: function */
/* frame size = 23 */
/* stack size = 41 */
.L__stack_usage = 41
	movw r6,r24
	std Y+16,r22
	mov r5,r20
	mov r4,r12
	mov r12,r14
.LVL1258:
	std Y+6,r15
	movw r2,r16
	std Y+10,r18
	std Y+12,r19
	std Y+20,r8
	std Y+21,r9
	std Y+22,r10
	std Y+23,r11
	ldd r8,Y+44
	ldd r9,Y+45
.LVL1259:
	ldd r16,Y+48
	ldd r17,Y+49
	ldd r18,Y+50
	ldd r19,Y+51
	ldd r20,Y+52
.LVL1260:
	ldd r21,Y+53
	ldd r22,Y+54
.LVL1261:
	ldd r23,Y+55
.LVL1262:
	.loc 11 439 0
	ldd r24,Y+60
	ldd r25,Y+61
.LVL1263:
	sbiw r24,0
	breq .L984
	movw r26,r24
	st X+,__zero_reg__
	st X,__zero_reg__
.LVL1264:
.L984:
	.loc 11 440 0
	cp r6,__zero_reg__
	cpc r7,__zero_reg__
	brne .L985
.LVL1265:
.L987:
	mov r4,__zero_reg__
.L983:
	.loc 11 492 0
	mov r24,r4
/* epilogue start */
	adiw r28,23
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
.LVL1266:
	pop r5
	pop r4
	pop r3
	pop r2
	ret
.LVL1267:
.L985:
	.loc 11 440 0
	movw r30,r6
	subi r30,-128
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
.LVL1268:
	std Y+3,r25
	std Y+2,r24
	or r24,r25
	breq .L987
	cp r8,__zero_reg__
	cpc r9,__zero_reg__
	breq .L987
	ldd r24,Y+46
	ldd r25,Y+47
	sbiw r24,2
	cpi r24,-65
	cpc r25,__zero_reg__
	brsh .L987
	movw r26,r8
	adiw r26,1
	ld r27,X
	std Y+4,r27
.LVL1269:
.LBB902:
.LBB903:
	.loc 11 362 0
	cpi r27,lo8(1)
	breq .L1215
	mov r24,r27
	andi r24,lo8(-3)
	cpi r24,lo8(16)
	breq .L1215
	ldi r24,lo8(1)
	ldi r25,0
	mov r30,r27
	subi r30,lo8(-(-64))
	cpi r30,lo8(9)
	brlo .L989
	ldi r25,0
	ldi r24,0
.L989:
.LVL1270:
.LBE903:
.LBE902:
	.loc 11 440 0
	or r24,r25
	brne .+2
	rjmp .L987
.L1215:
.LVL1271:
	.loc 11 441 0
	ldd r30,Y+2
	ldd r31,Y+3
	subi r30,-116
	sbci r31,-1
	ld r24,Z
	std Y+1,r24
	cpse r24,__zero_reg__
	rjmp .L987
	ldd r26,Y+2
	ldd r27,Y+3
	adiw r26,2
	ld r24,X+
	ld r25,X
	sbiw r26,2+1
	cp r24,r6
	cpc r25,r7
	breq .+2
	rjmp .L987
.LVL1272:
.LBB904:
.LBB905:
	.loc 1 606 0
	ldd r14,Y+56
	ldd r15,Y+57
	movw r24,r26
	call update
.LVL1273:
.LBE905:
.LBE904:
	.loc 11 442 0
	movw r24,r6
	call synchronize
.LVL1274:
.LBB906:
.LBB907:
	.loc 11 367 0
	movw r30,r8
	ld r24,Z
	cpi r24,lo8(2)
	breq .+2
	rjmp .L1092
.LVL1275:
	.loc 11 366 0
	ldd r17,Z+1
	.loc 11 368 0
	cpi r17,lo8(1)
	brne .+4
	jmp .L991
	.loc 11 369 0
	cpi r17,lo8(16)
	brne .+2
	rjmp .L1073
	.loc 11 370 0
	cpi r17,lo8(18)
	brne .+2
	rjmp .L1074
	.loc 11 371 0
	cpi r17,lo8(64)
	brne .+2
	rjmp .L1075
.LBE907:
.LBE906:
	.loc 11 372 0
	ldi r24,lo8(49)
	ldi r25,0
.LBB914:
.LBB908:
	cpi r17,lo8(67)
	brne .+2
	rjmp .L992
	.loc 11 373 0
	ldd r18,Y+46
	ldd r19,Y+47
	cpi r18,66
	cpc r19,__zero_reg__
	breq .+2
	rjmp .L1175
.LVL1276:
.L994:
	.loc 11 375 0
	movw r24,r8
	adiw r24,2
	call r32
.LVL1277:
	or r22,r23
	or r22,r24
	or r22,r25
	brne .+2
	rjmp .L1095
	movw r30,r8
	ldd r24,Z+6
	ldd r25,Z+7
	or r24,r25
	brne .+2
	rjmp .L1095
	.loc 11 376 0
	cpi r17,lo8(64)
	brlo .L995
	.loc 11 377 0
	movw r24,r8
	adiw r24,8
	call r32
.LVL1278:
	or r22,r23
	or r22,r24
	or r22,r25
	brne .+2
	rjmp .L1095
	movw r24,r8
	adiw r24,12
	call nonzero.constprop.2
.LVL1279:
	tst r24
	brne .+2
	rjmp .L1095
	.loc 11 378 0
	cpi r17,lo8(64)
	breq .L995
	.loc 11 379 0
	cpi r17,lo8(67)
	breq .+2
	rjmp .L996
	.loc 11 380 0
	movw r26,r8
	adiw r26,44
	ld r17,X
.LVL1280:
	cpi r17,lo8(3)
	brlo .+4
	jmp .L1081
	movw r24,r8
	adiw r24,45
	call r32
.LVL1281:
	.loc 11 381 0
	cpi r17,lo8(2)
	breq .L997
	or r22,r23
	or r22,r24
	or r22,r25
	breq .L995
.L1090:
.LBE908:
.LBE914:
	ldi r19,lo8(3)
	mov r5,r19
.LVL1282:
	rjmp .L990
.LVL1283:
.L1073:
	.loc 11 369 0
	ldi r24,lo8(72)
	ldi r25,0
.L992:
.LVL1284:
.LBB915:
.LBB909:
	.loc 11 373 0
	ldd r18,Y+46
	ldd r19,Y+47
	cp r18,r24
	cpc r19,r25
	brne .+2
	rjmp .L994
.LVL1285:
.L1175:
.LBE909:
.LBE915:
	ldi r16,lo8(2)
	mov r5,r16
.LVL1286:
	rjmp .L990
.LVL1287:
.L1074:
	.loc 11 370 0
	ldi r24,lo8(10)
	ldi r25,0
	rjmp .L992
.L1075:
	.loc 11 371 0
	ldi r24,lo8(-122)
	ldi r25,0
	rjmp .L992
.LVL1288:
.L997:
.LBB916:
.LBB910:
	.loc 11 381 0
	or r22,r23
	or r22,r24
	or r22,r25
	breq .L1090
.L995:
.LBE910:
.LBE916:
	.loc 11 444 0
	ldd r27,Y+16
	cpi r27,lo8(1)
	breq .+2
	rjmp .L1092
	cpse r5,__zero_reg__
	rjmp .L1092
	.loc 11 445 0
	ldd r21,Y+4
	cpi r21,lo8(1)
	breq .+2
	rjmp .L1245
	mov r18,r4
	mov r19,r13
	mov r20,r12
	ldd r21,Y+6
	movw r22,r2
	ldd r24,Y+10
	ldd r25,Y+12
	ldi r26,0
	call __cmpdi2_s8
	brne .+2
	rjmp .L990
.L1094:
	ldi r25,lo8(5)
	mov r5,r25
.LVL1289:
	rjmp .L990
.LVL1290:
.L996:
.LBB917:
.LBB911:
	.loc 11 384 0
	movw r24,r8
	adiw r24,44
	call r32
.LVL1291:
	or r22,r23
	or r22,r24
	or r22,r25
	brne .+2
	rjmp .L1095
	movw r24,r8
	adiw r24,48
	call r32
.LVL1292:
	or r22,r23
	or r22,r24
	or r22,r25
	brne .+2
	rjmp .L1095
	.loc 11 385 0
	mov r24,r17
	andi r24,lo8(-5)
	cpi r24,lo8(66)
	breq .L998
	movw r24,r8
	adiw r24,52
	call r64
.LVL1293:
	ldi r26,0
	call __cmpdi2_s8
	breq .+2
	rjmp .L1090
	.loc 11 386 0
	cpi r17,lo8(68)
	breq .L999
	cpi r17,lo8(72)
	breq .L999
.L998:
	movw r24,r8
	adiw r24,60
	call r32
.LVL1294:
	or r22,r23
	or r22,r24
	or r22,r25
	breq .+2
	rjmp .L1090
	movw r30,r8
	subi r30,-64
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	.loc 11 387 0
	cpi r17,lo8(69)
	breq .+4
	jmp .L1000
	sbiw r24,2
	brne .+2
	rjmp .L995
	rjmp .L1090
.L999:
	.loc 11 389 0
	movw r30,r8
	subi r30,-64
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	or r24,r25
	brne .+2
	rjmp .L995
	rjmp .L1090
.LVL1295:
.L1245:
.LBE911:
.LBE917:
	.loc 11 447 0
	ldd r30,Y+2
	ldd r31,Y+3
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	sbrs r24,0
	rjmp .L1093
	.loc 11 448 0
	ldd r30,Y+2
	ldd r31,Y+3
	ldd r18,Z+4
	ldd r19,Z+5
	ldd r20,Z+6
	ldd r21,Z+7
	ldd r22,Z+8
	ldd r23,Z+9
	ldd r24,Z+10
	ldd r25,Z+11
	mov r10,r4
	mov r11,r13
	ldd r13,Y+6
	movw r14,r2
	ldd r16,Y+10
	ldd r17,Y+12
	call __cmpdi2
	breq .+2
	rjmp .L1094
	.loc 11 449 0
	ldd r18,Y+20
	ldd r19,Y+21
	ldd r20,Y+22
	ldd r21,Y+23
	or r18,r19
	or r18,r20
	or r18,r21
	breq .L1095
.LVL1296:
.L990:
	.loc 11 451 0
	ldd r30,Y+2
	ldd r31,Y+3
	ldd r24,Z+36
	ldd r25,Z+37
	ldd r26,Z+38
	ldd r27,Z+39
	cpi r24,-1
	sbci r25,-1
	sbci r26,-1
	sbci r27,-1
	brne .L1002
	.loc 11 452 0
	ldd r24,Y+2
	ldd r25,Y+3
	call hms_endpoint_counter_fault
.LVL1297:
	movw r24,r6
	call synchronize
.LVL1298:
	.loc 11 453 0
	ldd r24,Y+4
	andi r24,lo8(-3)
	cpi r24,lo8(69)
	brne .+4
	jmp .L1003
	ldd r18,Y+4
	cpi r18,lo8(18)
	breq .+2
	rjmp .L987
	.loc 11 455 0
	cpse r5,__zero_reg__
	jmp .L1255
.L1007:
	.loc 11 460 0
	movw r22,r8
	ldd r24,Y+2
	ldd r25,Y+3
	call hms_endpoint_revoke_shared
.LVL1299:
	mov r13,r24
.LVL1300:
	movw r24,r6
	call synchronize
.LVL1301:
	.loc 11 461 0
	movw r26,r6
	adiw r26,4
	ld r24,X
	.loc 11 437 0
	mov r5,__zero_reg__
	.loc 11 461 0
	cpi r24,lo8(2)
	breq .+2
	rjmp .L1097
.LVL1302:
.L1256:
	.loc 11 437 0
	mov r4,__zero_reg__
	rjmp .L1005
.LVL1303:
.L1092:
	.loc 11 444 0
	clr r5
	inc r5
.LVL1304:
	rjmp .L990
.LVL1305:
.L1093:
	.loc 11 447 0
	ldi r18,lo8(18)
	mov r5,r18
.LVL1306:
	rjmp .L990
.LVL1307:
.L1095:
	.loc 11 449 0
	ldi r24,lo8(11)
	mov r5,r24
.LVL1308:
	rjmp .L990
.LVL1309:
.L1002:
	.loc 11 455 0
	cpse r5,__zero_reg__
	jmp .L1255
	.loc 11 456 0
	ldd r19,Y+4
	cpi r19,lo8(18)
	breq .L1007
	brlo .+2
	rjmp .L1008
	cpi r19,lo8(1)
	brne .+2
	rjmp .L1009
	cpi r19,lo8(16)
	brne .+2
	rjmp .L1010
.L1006:
.LVL1310:
.LBB918:
.LBB919:
	.loc 11 268 0
	movw r22,r8
	movw r24,r6
	call reference.lto_priv.16
.LVL1311:
	mov r13,r24
.LVL1312:
	.loc 11 269 0
	movw r24,r8
	adiw r24,44
	call r32
.LVL1313:
	std Y+6,r22
	std Y+7,r23
	std Y+8,r24
	std Y+9,r25
.LVL1314:
	movw r10,r6
	ldi r18,9
	add r10,r18
	adc r11,__zero_reg__
	movw r24,r10
	call r32
.LVL1315:
	movw r2,r22
	movw r4,r24
.LVL1316:
	.loc 11 270 0
	cpse r13,__zero_reg__
	rjmp .L1028
	.loc 11 271 0
	ldd r24,Y+6
	ldd r25,Y+7
	ldd r26,Y+8
	ldd r27,Y+9
	cp r24,r2
	cpc r25,r3
	cpc r26,r4
	cpc r27,r5
	breq .+2
	rjmp .L1029
	or r24,r25
	or r24,r26
	or r24,r27
	brne .+2
	rjmp .L1152
	.loc 11 272 0
	ldi r20,lo8(2)
	ldi r21,0
	movw r22,r8
	movw r24,r6
	adiw r24,13
	call memcmp
.LVL1317:
	or r24,r25
	brne .L1151
	movw r22,r8
	subi r22,-48
	sbci r23,-1
	ldi r20,lo8(18)
	ldi r21,0
	movw r24,r6
	adiw r24,15
	call memcmp
.LVL1318:
	or r24,r25
	brne .+2
	rjmp .L1028
.L1151:
.LBE919:
.LBE918:
	ldi r22,lo8(9)
	mov r13,r22
.LVL1319:
	rjmp .L1028
.LVL1320:
.L1008:
	.loc 11 456 0
	ldd r20,Y+4
	cpi r20,lo8(64)
	brne .+2
	rjmp .L1011
	cpi r20,lo8(67)
	breq .+2
	rjmp .L1006
	.loc 11 464 0
	movw r22,r8
	movw r24,r6
	call reference.lto_priv.16
.LVL1321:
	std Y+1,r24
.LVL1322:
	movw r30,r8
	ldd r4,Z+44
.LVL1323:
	.loc 11 465 0
	cpse r24,__zero_reg__
	rjmp .L1143
	ldi r31,lo8(2)
	.loc 11 437 0
	ldd r5,Y+1
	.loc 11 465 0
	cpse r4,r31
	rjmp .L1147
	movw r24,r8
.LVL1324:
	adiw r24,45
	call r32
.LVL1325:
	movw r10,r22
	movw r12,r24
.LVL1326:
.LBB938:
.LBB939:
	.loc 11 426 0
	movw r24,r6
	adiw r24,45
	call r32
.LVL1327:
	cp r22,r10
	cpc r23,r11
	cpc r24,r12
	cpc r25,r13
	brlo .+2
	rjmp .L1145
	.loc 11 427 0
	movw r24,r6
	adiw r24,41
	call r32
.LVL1328:
	cp r22,r10
	cpc r23,r11
	cpc r24,r12
	cpc r25,r13
	brsh .+2
	rjmp .L1146
	.loc 11 428 0
	movw r30,r6
	subi r30,-103
	sbci r31,-1
	ld r3,Z
.LBE939:
.LBE938:
	mov r15,__zero_reg__
.LBB944:
.LBB942:
.LBB940:
	.loc 11 429 0
	movw r16,r6
	subi r16,-102
	sbci r17,-1
	.loc 11 430 0
	movw r18,r6
	subi r18,124
	sbci r19,-1
	std Y+5,r19
	std Y+4,r18
.LVL1329:
	ldi r27,lo8(44)
	mov r2,r27
.LVL1330:
.L1026:
.LBE940:
	.loc 11 428 0
	cp r15,r3
	brne .+2
	rjmp .L1148
	ldi r31,lo8(2)
	cpse r15,r31
	rjmp .L1027
.LBE942:
.LBE944:
	.loc 11 437 0
	mov r5,__zero_reg__
	.loc 11 464 0
	ldi r26,lo8(2)
	mov r4,r26
.LVL1331:
.L1247:
	.loc 11 432 0
	ldi r24,lo8(4)
	mov r13,r24
	rjmp .L1005
.LVL1332:
.L1009:
	.loc 11 457 0
	movw r26,r8
	adiw r26,2
	ld r4,X
.LVL1333:
	mov r13,__zero_reg__
	ldi r27,lo8(1)
	std Y+1,r27
.LVL1334:
.L1005:
	.loc 11 470 0
	ldd r30,Y+2
	ldd r31,Y+3
	subi r30,-74
	sbci r31,-1
.LVL1335:
	ld r14,Z
	ldd r15,Z+1
	ldi r18,95
	and r14,r18
	clr r15
.LVL1336:
.LBB945:
.LBB946:
	.loc 1 606 0
	ldd r26,Y+2
	ldd r27,Y+3
	adiw r26,12
	ld r16,X
	sbiw r26,12
	adiw r26,13
	ld r17,X
	sbiw r26,13
	adiw r26,14
	ld r18,X
	sbiw r26,14
	adiw r26,15
	ld r19,X
	sbiw r26,15
	adiw r26,16
	ld r20,X
	sbiw r26,16
	adiw r26,17
	ld r21,X
	sbiw r26,17
	adiw r26,18
	ld r22,X
	sbiw r26,18
	adiw r26,19
	ld r23,X
	sbiw r26,19
	movw r24,r26
	call update
.LVL1337:
.LBE946:
.LBE945:
	.loc 11 470 0
	movw r24,r6
	call synchronize
.LVL1338:
	.loc 11 471 0
	ldd r30,Y+2
	ldd r31,Y+3
	ldd r24,Z+36
	ldd r25,Z+37
	ldd r26,Z+38
	ldd r27,Z+39
	cpi r24,-1
	ldi r31,-1
	cpc r25,r31
	cpc r26,r31
	cpc r27,r31
	brne .+2
	rjmp .L987
	.loc 11 472 0
	adiw r24,1
	adc r26,__zero_reg__
	adc r27,__zero_reg__
	ldd r30,Y+2
	ldd r31,Y+3
	std Z+36,r24
	std Z+37,r25
	std Z+38,r26
	std Z+39,r27
	.loc 11 473 0
	ldd r18,Y+58
	ldd r19,Y+59
	or r18,r19
	breq .+2
	rjmp .L1054
.L1259:
	.loc 11 491 0
	clr r4
	inc r4
.LVL1339:
	rjmp .L983
.LVL1340:
.L1010:
	.loc 11 458 0
	movw r22,r8
	ldd r24,Y+2
	ldd r25,Y+3
	call hms_endpoint_bind_shared
.LVL1341:
	mov r13,r24
.LVL1342:
	ldi r30,lo8(1)
	std Y+1,r30
.LVL1343:
.L1248:
	.loc 11 461 0
	clr r4
	inc r4
	rjmp .L1005
.LVL1344:
.L1011:
.LBB947:
.LBB948:
	.loc 11 195 0
	movw r30,r6
	subi r30,-128
	sbci r31,-1
	ld r2,Z
	ldd r3,Z+1
.LVL1345:
	.loc 11 196 0
	movw r24,r8
	adiw r24,8
	call r32
.LVL1346:
	std Y+6,r22
	std Y+7,r23
	std Y+8,r24
	std Y+9,r25
.LVL1347:
	movw r30,r6
	ldd r4,Z+4
.LVL1348:
	movw r24,r6
	call r32
.LVL1349:
	.loc 11 197 0
	ldi r31,lo8(2)
	cpse r4,r31
	rjmp .L1013
	ldd r18,Y+6
	ldd r19,Y+7
	ldd r20,Y+8
	ldd r21,Y+9
	cp r18,r22
	cpc r19,r23
	cpc r20,r24
	cpc r21,r25
	brne .L1013
	.loc 11 198 0
	ldi r20,lo8(-122)
	ldi r21,0
	movw r22,r8
	movw r24,r2
	subi r24,-117
	sbci r25,-1
	call memcmp
.LVL1350:
.LBE948:
.LBE947:
	.loc 11 437 0
	std Y+1,__zero_reg__
	mov r4,__zero_reg__
	.loc 11 198 0
	ldi r17,lo8(9)
	mov r13,r17
.LBB974:
.LBB966:
	or r24,r25
	breq .+2
	rjmp .L1005
.LVL1351:
.L1147:
.LBE966:
.LBE974:
	.loc 11 430 0
	mov r13,__zero_reg__
	rjmp .L1005
.LVL1352:
.L1013:
.LBB975:
.LBB967:
	.loc 11 199 0
	ldd r18,Y+6
	ldd r19,Y+7
	ldd r20,Y+8
	ldd r21,Y+9
	cp r22,r18
	cpc r23,r19
	cpc r24,r20
	cpc r25,r21
	brlo .+2
	rjmp .L1099
	.loc 11 200 0
	cpse r4,__zero_reg__
	rjmp .L1100
	movw r30,r2
	subi r30,-110
	sbci r31,-1
	ld r5,Z
.LVL1353:
	cpse r5,__zero_reg__
	rjmp .L1101
	subi r30,23
	sbci r31,-1
	ld r19,Z
	std Y+1,r19
	cpse r19,__zero_reg__
	rjmp .L1102
	.loc 11 201 0
	subi r30,-22
	sbc r31,__zero_reg__
	ld r4,Z
	tst r4
	brne .+2
	rjmp .L1141
	sbiw r30,1
	ld r24,Z
	subi r24,lo8(-(-1))
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L1104
	.loc 11 202 0
	movw r20,r8
	subi r20,-2
	sbci r21,-1
	std Y+19,r21
	std Y+18,r20
	movw r24,r20
	call r32
.LVL1354:
	.loc 11 201 0
	movw r26,r2
	adiw r26,28
	ld r16,X+
	ld r17,X+
	ld r18,X+
	ld r19,X
	sbiw r26,28+3
	cp r22,r16
	cpc r23,r17
	cpc r24,r18
	cpc r25,r19
	breq .+2
	rjmp .L1104
	.loc 11 202 0
	movw r30,r8
	ldd r24,Z+6
	ldd r25,Z+7
	eor r25,r24
	eor r24,r25
	eor r25,r24
	movw r30,r2
	subi r30,-72
	sbci r31,-1
	ld r18,Z
	ldd r19,Z+1
	cp r24,r18
	cpc r25,r19
	breq .+2
	rjmp .L1104
	.loc 11 203 0
	movw r24,r2
	call hms_endpoint_readiness
.LVL1355:
	mov r4,r24
.LVL1356:
	cpse r24,__zero_reg__
	rjmp .L1107
	.loc 11 204 0
	movw r26,r8
	adiw r26,44
	ld r24,X+
	ld r25,X
	cp r24,__zero_reg__
	sbci r25,1
	breq .+2
	rjmp .L1108
	.loc 11 205 0
	movw r30,r8
	ldd r24,Z+46
	cpi r24,lo8(32)
	breq .+2
	rjmp .L1127
	movw r18,r8
	subi r18,-47
	sbci r19,-1
	std Y+11,r19
	std Y+10,r18
.LVL1357:
.LBB949:
.LBB950:
.LBB951:
.LBB952:
	.loc 11 32 0
	movw r24,r18
	call r32
.LVL1358:
	movw r12,r22
	movw r14,r24
.LVL1359:
.LBE952:
.LBE951:
	.loc 11 162 0
	ldi r19,96
	cp r12,r19
	ldi r19,121
	cpc r13,r19
	ldi r19,-2
	cpc r14,r19
	ldi r19,-1
	cpc r15,r19
	brge .+2
	rjmp .L1127
.LVL1360:
.LBB953:
.LBB954:
	.loc 11 32 0
	movw r24,r8
	adiw r24,51
.LVL1361:
	call r32
.LVL1362:
.LBE954:
.LBE953:
	.loc 11 162 0
	cpi r22,65
	ldi r20,13
	cpc r23,r20
	ldi r20,3
	cpc r24,r20
	cpc r25,__zero_reg__
	brlt .+2
	rjmp .L1127
	cp r12,r22
	cpc r13,r23
	cpc r14,r24
	cpc r15,r25
	brlt .+2
	rjmp .L1127
.LVL1363:
.LBB955:
.LBB956:
	.loc 11 32 0
	movw r24,r8
	adiw r24,55
.LVL1364:
	call r32
.LVL1365:
.LBE956:
.LBE955:
	.loc 11 162 0
	cpi r22,-31
	sbci r23,-109
	sbci r24,4
	cpc r25,__zero_reg__
	brlo .+2
	rjmp .L1127
.LVL1366:
.LBB957:
.LBB958:
	.loc 11 32 0
	movw r24,r8
	adiw r24,59
.LVL1367:
	call r32
.LVL1368:
.LBE958:
.LBE957:
	.loc 11 163 0
	subi r22,1
	sbc r23,__zero_reg__
	sbc r24,__zero_reg__
	sbc r25,__zero_reg__
	cpi r22,-96
	sbci r23,-122
	sbci r24,1
	cpc r25,__zero_reg__
	brlo .+2
	rjmp .L1127
	.loc 11 164 0
	movw r30,r8
	subi r30,-75
	sbci r31,-1
	.loc 11 163 0
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1127
	.loc 11 164 0
	adiw r30,1
	ld r24,Z
	cpi r24,lo8(1)
	breq .+2
	rjmp .L1127
	adiw r30,1
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1127
	adiw r30,1
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1127
	sbiw r30,15
.LBE950:
.LBE949:
.LBE967:
.LBE975:
	.loc 11 165 0
	ldi r24,lo8(16)
.L1015:
.LVL1369:
	ld r18,Z+
	ld r19,Z+
.LVL1370:
	eor r19,r18
	eor r18,r19
	eor r19,r18
.LVL1371:
.LBB976:
.LBB968:
.LBB961:
.LBB960:
.LBB959:
	.loc 11 167 0
	cpi r18,97
	ldi r27,-22
	cpc r19,r27
	brlo .+2
	rjmp .L1127
	or r18,r19
	brne .L1014
	cpi r24,lo8(22)
	breq .L1014
	cpi r24,lo8(24)
	breq .+2
	rjmp .L1127
.L1014:
.LBE959:
	.loc 11 165 0
	subi r24,lo8(-(2))
.LVL1372:
	cpi r24,lo8(28)
	brne .L1015
.LVL1373:
	movw r30,r8
	adiw r30,63
	ld r24,Z
	ldd r25,Z+1
.LVL1374:
	eor r25,r24
	eor r24,r25
	eor r25,r24
.LVL1375:
	.loc 11 169 0
	adiw r30,2
	ld r18,Z
	ldd r19,Z+1
	eor r19,r18
	eor r18,r19
	eor r19,r18
	cp r24,r18
	cpc r25,r19
	brlo .+2
	rjmp .L1127
	adiw r30,2
	ld r18,Z
	ldd r19,Z+1
	eor r19,r18
	eor r18,r19
	eor r19,r18
	cp r24,r18
	cpc r25,r19
	brlo .+2
	rjmp .L1127
	adiw r30,6
	ld r18,Z
	ldd r19,Z+1
	eor r19,r18
	eor r18,r19
	eor r19,r18
	ldi r20,lo8(1)
	ldi r21,0
	cp r24,r18
	cpc r25,r19
	brlo .L1017
	ldi r21,0
	ldi r20,0
.L1017:
.LVL1376:
.LBE960:
.LBE961:
	.loc 11 205 0
	or r20,r21
	brne .+2
	rjmp .L1127
	movw r24,r8
	adiw r24,12
	call nonzero.constprop.2
.LVL1377:
	std Y+1,r24
	tst r24
	brne .+2
	rjmp .L1124
	.loc 11 206 0
	movw r24,r8
	subi r24,-122
	sbci r25,-1
	call r32
.LVL1378:
	.loc 11 205 0
	or r22,r23
	or r22,r24
	or r22,r25
	brne .+2
	rjmp .L1127
	.loc 11 206 0
	movw r30,r8
	subi r30,-126
	sbci r31,-1
	std Y+13,r31
	std Y+12,r30
	movw r24,r30
	call r32
.LVL1379:
	or r22,r23
	or r22,r24
	or r22,r25
	brne .+2
	rjmp .L1127
	movw r24,r8
	subi r24,126
	sbci r25,-1
	call r32
.LVL1380:
	or r22,r23
	or r22,r24
	or r22,r25
	brne .+2
	rjmp .L1127
	.loc 11 207 0
	movw r30,r8
	subi r30,-120
	sbci r31,-1
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1129
	adiw r30,1
	ld r24,Z
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L1129
	movw r30,r2
	subi r30,-74
	sbci r31,-1
	.loc 11 208 0
	cpse r24,__zero_reg__
	rjmp .L1018
	ld r24,Z
	sbrc r24,3
	rjmp .L1019
.L1131:
.LBE968:
.LBE976:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	.loc 11 209 0
	ldi r30,lo8(17)
	mov r13,r30
	rjmp .L1005
.L1018:
.LBB977:
.LBB969:
	ld r24,Z
	sbrs r24,2
	rjmp .L1131
.L1019:
	.loc 11 210 0
	movw r30,r8
	subi r30,-79
	sbci r31,-1
	ld r14,Z
	movw r30,r6
	subi r30,126
	sbci r31,-1
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	ldd r24,Z+14
	cpse r14,r24
	rjmp .L1132
	movw r18,r8
	subi r18,-80
	sbci r19,-1
	std Y+5,r19
	std Y+4,r18
.LVL1381:
	std Y+17,r3
	std Y+16,r2
.LVL1382:
	movw r16,r2
	movw r10,r18
	mov r13,__zero_reg__
	mov r12,__zero_reg__
.LBB962:
	.loc 11 213 0
	mov r15,__zero_reg__
.L1022:
.LVL1383:
	.loc 11 212 0
	movw r24,r10
	call r32
.LVL1384:
	.loc 11 213 0
	movw r18,r14
	mov r0,r12
	rjmp 2f
	1:
	asr r19
	ror r18
	2:
	dec r0
	brpl 1b
	sbrs r18,0
	rjmp .L1020
	cp r22,__zero_reg__
	cpc r23,__zero_reg__
	cpc r24,__zero_reg__
	cpc r25,__zero_reg__
	breq .L1134
	movw r26,r16
	adiw r26,40
	ld r18,X+
	ld r19,X+
	ld r20,X+
	ld r21,X
	sbiw r26,40+3
	cp r18,r22
	cpc r19,r23
	cpc r20,r24
	cpc r21,r25
	brlo .L1021
.L1134:
.LBE962:
.LBE969:
.LBE977:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	.loc 11 213 0
	ldi r22,lo8(13)
	mov r13,r22
.LVL1385:
	rjmp .L1005
.LVL1386:
.L1020:
.LBB978:
.LBB970:
.LBB963:
	.loc 11 214 0
	or r22,r23
	or r22,r24
	or r22,r25
	breq .+2
	rjmp .L1135
.L1021:
.LVL1387:
	ldi r27,-1
	sub r12,r27
	sbc r13,r27
.LVL1388:
	ldi r30,4
	add r10,r30
	adc r11,__zero_reg__
	subi r16,-4
	sbci r17,-1
.LBE963:
	.loc 11 211 0
	ldi r31,8
	cp r12,r31
	cpc r13,__zero_reg__
	brne .L1022
	.loc 11 216 0
	ldi r20,lo8(1)
	ldd r22,Y+10
	ldd r23,Y+11
.LVL1389:
	movw r24,r6
	call installed_guard
.LVL1390:
	mov r13,r24
.LVL1391:
	.loc 11 217 0
	ldd r22,Y+12
	ldd r23,Y+13
	movw r24,r6
	call source_bindings
.LVL1392:
	cpse r24,__zero_reg__
	rjmp .L1023
.LBE970:
.LBE978:
	ldi r17,lo8(26)
	mov r13,r17
.LVL1393:
.L1023:
.LBB979:
.LBB971:
.LBB964:
.LBB965:
	.loc 1 607 0
	movw r24,r2
	call sample_clock
.LVL1394:
.LBE965:
.LBE964:
.LBE971:
.LBE979:
	.loc 11 437 0
	mov r5,__zero_reg__
.LBB980:
.LBB972:
	.loc 11 219 0
	cpse r13,__zero_reg__
	rjmp .L1250
	.loc 11 220 0
	movw r24,r2
	call hms_endpoint_readiness
.LVL1395:
	mov r4,r24
.LVL1396:
	cpse r24,__zero_reg__
	rjmp .L1138
	.loc 11 221 0
	movw r30,r2
	subi r30,-109
	sbci r31,-1
	ld r18,Z
	std Y+1,r18
	tst r18
	brne .+2
	rjmp .L1139
	ldd r24,Y+18
	ldd r25,Y+19
	call r32
.LVL1397:
	movw r26,r2
	adiw r26,28
	ld r16,X+
	ld r17,X+
	ld r18,X+
	ld r19,X
	sbiw r26,28+3
	cp r22,r16
	cpc r23,r17
	cpc r24,r18
	cpc r25,r19
	breq .+2
	rjmp .L1141
	movw r30,r8
	ldd r24,Z+6
	ldd r25,Z+7
	eor r25,r24
	eor r24,r25
	eor r25,r24
	movw r30,r2
	subi r30,-72
	sbci r31,-1
	ld r18,Z
	ldd r19,Z+1
	cp r24,r18
	cpc r25,r19
	breq .+2
	rjmp .L1141
	.loc 11 222 0
	movw r10,r8
	ldi r31,112
	add r10,r31
	adc r11,__zero_reg__
	movw r24,r10
	call r64
.LVL1398:
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r6
	subi r24,-128
	sbci r25,-1
	call lease_valid.isra.2
.LVL1399:
	std Y+1,r24
	tst r24
	brne .+2
	rjmp .L1142
	.loc 11 224 0
	ldi r24,lo8(-128)
	movw r26,r6
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	ldd r20,Y+6
	ldd r21,Y+7
	ldd r22,Y+8
	ldd r23,Y+9
	movw r24,r6
	call w32
.LVL1400:
	.loc 11 225 0
	ldi r24,lo8(2)
	movw r30,r6
	std Z+4,r24
	ldi r20,lo8(1)
	ldi r21,0
	ldi r22,0
	ldi r23,0
	movw r24,r6
	adiw r24,5
	call w32
.LVL1401:
	.loc 11 226 0
	ldi r24,lo8(-122)
	movw r30,r8
	movw r26,r2
	subi r26,-117
	sbci r27,-1
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(-122)
	movw r30,r2
	subi r30,-110
	sbci r31,-1
	st Z,r24
.LVL1402:
	mov r15,__zero_reg__
	mov r14,__zero_reg__
	.loc 11 227 0
	movw r16,r8
	subi r16,-79
	sbci r17,-1
.LVL1403:
.L1025:
	movw r26,r16
	ld r24,X
	ldi r25,0
	mov r0,r14
	rjmp 2f
	1:
	asr r25
	ror r24
	2:
	dec r0
	brpl 1b
	sbrs r24,0
	rjmp .L1024
	ldd r24,Y+4
	ldd r25,Y+5
	call r32
.LVL1404:
	ldd r30,Y+16
	ldd r31,Y+17
	std Z+40,r22
	std Z+41,r23
	std Z+42,r24
	std Z+43,r25
.L1024:
.LVL1405:
	ldi r31,-1
	sub r14,r31
	sbc r15,r31
.LVL1406:
	ldd r18,Y+4
	ldd r19,Y+5
	subi r18,-4
	sbci r19,-1
	std Y+5,r19
	std Y+4,r18
	ldd r20,Y+16
	ldd r21,Y+17
	subi r20,-4
	sbci r21,-1
	std Y+17,r21
	std Y+16,r20
	ldi r21,8
	cp r14,r21
	cpc r15,__zero_reg__
	brne .L1025
	.loc 11 228 0
	movw r30,r2
	subi r30,-53
	sbci r31,-2
	ldi r24,lo8(69)
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	.loc 11 229 0
	movw r30,r2
	std Z+20,__zero_reg__
	std Z+21,__zero_reg__
	std Z+22,__zero_reg__
	std Z+23,__zero_reg__
	std Z+24,__zero_reg__
	std Z+25,__zero_reg__
	std Z+26,__zero_reg__
	std Z+27,__zero_reg__
	subi r30,-108
	sbci r31,-1
	clr r13
	inc r13
	st Z,r13
	adiw r30,3
	st Z,__zero_reg__
	.loc 11 230 0
	movw r14,r6
.LVL1407:
	ldi r31,-124
	add r14,r31
	adc r15,__zero_reg__
	movw r30,r14
	ld r26,Z
	ldd r27,Z+1
	subi r26,-64
	sbci r27,-1
	ldi r24,lo8(32)
	ldd r30,Y+10
	ldd r31,Y+11
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r26,r14
	ld r30,X+
	ld r31,X
	subi r30,-96
	sbci r31,-1
	ldi r24,lo8(24)
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	.loc 11 231 0
	movw r26,r14
	ld r30,X+
	ld r31,X
	subi r30,-120
	sbci r31,-1
	ldi r24,lo8(48)
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	movw r26,r14
	ld r30,X+
	ld r31,X
	subi r30,88
	sbci r31,-1
	ldi r24,lo8(88)
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	.loc 11 232 0
	ldi r24,lo8(8)
	ldd r30,Y+12
	ldd r31,Y+13
	movw r26,r6
	subi r26,-81
	sbci r27,-1
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r24,r10
	call r64
.LVL1408:
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r6
	adiw r24,33
	call w64
.LVL1409:
	.loc 11 233 0
	movw r30,r2
	ldd r16,Z+12
	ldd r17,Z+13
	ldd r18,Z+14
	ldd r19,Z+15
	ldd r20,Z+16
	ldd r21,Z+17
	ldd r22,Z+18
	ldd r23,Z+19
	movw r24,r6
	adiw r24,49
	call w64
.LVL1410:
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	movw r24,r6
	adiw r24,57
	call w64
.LVL1411:
	.loc 11 234 0
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	movw r24,r6
	subi r24,-65
	sbci r25,-1
	call w64
.LVL1412:
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	movw r24,r6
	subi r24,-73
	sbci r25,-1
	call w64
.LVL1413:
	.loc 11 235 0
	movw r26,r2
	adiw r26,12
	ld r16,X
	sbiw r26,12
	adiw r26,13
	ld r17,X
	sbiw r26,13
	adiw r26,14
	ld r18,X
	sbiw r26,14
	adiw r26,15
	ld r19,X
	sbiw r26,15
	adiw r26,16
	ld r20,X
	sbiw r26,16
	adiw r26,17
	ld r21,X
	sbiw r26,17
	adiw r26,18
	ld r22,X
	sbiw r26,18
	adiw r26,19
	ld r23,X
	movw r30,r14
	ld r24,Z
	ldd r25,Z+1
	subi r24,-96
	sbci r25,-1
	call w64
.LVL1414:
	.loc 11 236 0
	movw r26,r14
	ld r24,X+
	ld r25,X
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	subi r24,-104
	sbci r25,-1
	call w64
.LVL1415:
	.loc 11 237 0
	movw r30,r6
	subi r30,-93
	sbci r31,-1
	st Z,r13
	movw r30,r8
	subi r30,-79
	sbci r31,-1
	ld r24,Z
	movw r30,r6
	subi r30,-96
	sbci r31,-1
	st Z,r24
	ldi r24,lo8(-1)
	adiw r30,8
	st Z,r24
.LBE972:
.LBE980:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	rjmp .L1147
.LVL1416:
.L1027:
.LBB981:
.LBB943:
.LBB941:
	.loc 11 429 0
	movw r26,r16
	ld r5,X
	add r5,r15
	mov r27,r5
	andi r27,lo8(1)
	mov r5,r27
.LVL1417:
	.loc 11 430 0
	mul r27,r2
	movw r24,r0
	clr __zero_reg__
	subi r24,88
	sbci r25,-1
	ldd r30,Y+4
	ldd r31,Y+5
	ld r18,Z
	ldd r19,Z+1
	add r24,r18
	adc r25,r19
	call r32
.LVL1418:
	cp r10,r22
	cpc r11,r23
	cpc r12,r24
	cpc r13,r25
	brne .+2
	rjmp .L1147
.LBE941:
	.loc 11 428 0
	inc r15
.LVL1419:
	rjmp .L1026
.LVL1420:
.L1029:
.LBE943:
.LBE981:
.LBB982:
.LBB932:
	.loc 11 274 0
	ldd r18,Y+6
	ldd r19,Y+7
	ldd r20,Y+8
	ldd r21,Y+9
	cp r2,r18
	cpc r3,r19
	cpc r4,r20
	cpc r5,r21
	brlo .+2
	rjmp .L1152
	.loc 11 275 0
	ldi r19,-1
	cp r2,r19
	cpc r3,r19
	cpc r4,r19
	cpc r5,r19
	breq .L1030
	movw r20,r6
	subi r20,-5
	sbci r21,-1
	std Y+11,r21
	std Y+10,r20
	movw r24,r20
.LVL1421:
	call r32
.LVL1422:
	std Y+12,r22
	std Y+13,r23
	std Y+14,r24
	std Y+15,r25
	cpi r22,-1
	sbci r23,-1
	sbci r24,-1
	sbci r25,-1
	brne .L1031
.L1030:
	.loc 11 276 0
	ldi r22,0
	ldi r23,lo8(4)
	movw r24,r6
	call add_flags
.LVL1423:
	ldi r22,lo8(14)
	ldi r23,0
	movw r24,r6
	call unknown
.LVL1424:
	movw r30,r6
	subi r30,-128
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	call hms_endpoint_counter_fault
.LVL1425:
.L1172:
.LBE932:
.LBE982:
	.loc 11 318 0
	ldi r16,lo8(19)
	mov r13,r16
	rjmp .L1028
.LVL1426:
.L1031:
.LBB983:
.LBB933:
	.loc 11 278 0
	ldi r24,-1
	sub r2,r24
	sbc r3,r24
	sbc r4,r24
	sbc r5,r24
.LVL1427:
	ldd r18,Y+6
	ldd r19,Y+7
	ldd r20,Y+8
	ldd r21,Y+9
	cp r18,r2
	cpc r19,r3
	cpc r20,r4
	cpc r21,r5
	breq .+2
	rjmp .L1153
	.loc 11 279 0
	movw r14,r8
	ldi r19,48
	add r14,r19
	adc r15,__zero_reg__
	movw r24,r14
	call r32
.LVL1428:
	ldd r18,Y+12
	ldd r19,Y+13
	ldd r20,Y+14
	ldd r21,Y+15
	cp r18,r22
	cpc r19,r23
	cpc r20,r24
	cpc r21,r25
	breq .+2
	rjmp .L1171
	.loc 11 268 0
	movw r26,r8
	adiw r26,1
	ld r30,X
	movw r26,r6
	subi r26,-93
	sbci r27,-1
	ld r24,X
	.loc 11 280 0
	ldi r31,lo8(-65)
	mov r12,r31
	add r12,r30
	ldi r27,lo8(7)
	cp r27,r12
	brsh .+2
	rjmp .L1155
	mov r30,r12
	ldi r31,0
	subi r30,lo8(-(gs(.L1033)))
	sbci r31,hi8(-(gs(.L1033)))
	jmp __tablejump2__
	.p2align	1
.L1033:
	.word gs(.L1032)
	.word gs(.L1034)
	.word gs(.L1155)
	.word gs(.L1035)
	.word gs(.L1036)
	.word gs(.L1037)
	.word gs(.L1038)
	.word gs(.L1039)
.L1032:
	.loc 11 282 0
	cpi r24,lo8(1)
	breq .L1040
.LVL1429:
.L1041:
.LBE933:
.LBE983:
	ldi r23,lo8(4)
	mov r13,r23
.LVL1430:
.L1028:
	.loc 11 467 0
	ldi r24,lo8(1)
	ldd r30,Y+4
	cpi r30,lo8(72)
	breq .L1053
	ldi r24,0
.L1053:
	mov r4,r24
	neg r4
.L1251:
	.loc 11 437 0
	mov r5,__zero_reg__
	rjmp .L1005
.LVL1431:
.L1040:
.LBB984:
.LBB934:
	.loc 11 283 0
	ldi r22,lo8(1)
	movw r24,r6
	call guarded
.LVL1432:
	cpse r24,__zero_reg__
	rjmp .L1170
	.loc 11 284 0
	movw r30,r6
	subi r30,-93
	sbci r31,-1
	ld r24,Z
.LVL1433:
	cpi r24,lo8(1)
	brne .L1041
	.loc 11 285 0
	adiw r30,39
	ld r16,Z
	ldd r17,Z+1
.LVL1434:
.LBB920:
.LBB921:
	.loc 11 32 0
	movw r24,r16
	subi r24,112
	sbci r25,-1
.LVL1435:
	call r32
.LVL1436:
.LBE921:
.LBE920:
	.loc 11 285 0
	or r22,r23
	or r22,r24
	or r22,r25
	brne .L1158
	movw r30,r16
	subi r30,-116
	sbci r31,-1
	ld r24,Z
	tst r24
	brne .+2
	rjmp .L1038
.L1158:
.LBE934:
.LBE984:
	ldi r19,lo8(26)
	mov r13,r19
	rjmp .L1028
.LVL1437:
.L1034:
.LBB985:
.LBB935:
	.loc 11 288 0
	cpi r24,lo8(2)
	brne .L1041
	.loc 11 289 0
	ldi r22,lo8(1)
	movw r24,r6
	call guarded
.LVL1438:
	cpse r24,__zero_reg__
	rjmp .L1170
	.loc 11 290 0
	movw r30,r6
	subi r30,-93
	sbci r31,-1
	ld r24,Z
.LVL1439:
	cpi r24,lo8(2)
	brne .L1165
	movw r4,r8
	ldi r30,52
	add r4,r30
	adc r5,__zero_reg__
	movw r24,r4
	call r64
.LVL1440:
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r6
	subi r24,-128
	sbci r25,-1
	call lease_valid.isra.2
.LVL1441:
	tst r24
	breq .L1165
	ldi r20,lo8(8)
	ldi r21,0
	movw r22,r6
	subi r22,-33
	sbci r23,-1
	movw r24,r4
	call memcmp
.LVL1442:
	cp __zero_reg__,r24
	cpc __zero_reg__,r25
	brge .+2
	rjmp .L1038
.LVL1443:
.L1165:
.LBE935:
.LBE985:
	.loc 11 304 0
	ldi r18,lo8(16)
	mov r13,r18
	rjmp .L1028
.LVL1444:
.L1035:
.LBB986:
.LBB936:
	.loc 11 293 0
	movw r24,r8
	adiw r24,60
	call r32
.LVL1445:
	movw r20,r22
	movw r22,r24
.LVL1446:
.L1261:
	.loc 11 311 0
	movw r24,r6
	call ack_valid
.LVL1447:
	tst r24
	breq .L1043
.L1170:
	mov r13,r24
	rjmp .L1028
.LVL1448:
.L1036:
	.loc 11 296 0
	subi r24,lo8(-(-1))
	cpi r24,lo8(2)
	brlo .+2
	rjmp .L1041
.LVL1449:
.L1043:
	.loc 11 317 0
	movw r26,r8
	ld r24,X+
	ld r25,X
	movw r30,r6
	std Z+14,r25
	std Z+13,r24
	ldi r24,lo8(18)
	movw r30,r14
	movw r26,r6
	adiw r26,15
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 318 0
	ldd r20,Y+6
	ldd r21,Y+7
	ldd r22,Y+8
	ldd r23,Y+9
	movw r24,r10
	call w32
.LVL1450:
	movw r24,r6
	call bump
.LVL1451:
	tst r24
	brne .+2
	rjmp .L1172
	.loc 11 319 0
	ldi r31,lo8(7)
	cp r31,r12
	brsh .+2
	rjmp .L1028
	mov r30,r12
	ldi r31,0
	subi r30,lo8(-(gs(.L1045)))
	sbci r31,hi8(-(gs(.L1045)))
	jmp __tablejump2__
	.p2align	1
.L1045:
	.word gs(.L1044)
	.word gs(.L1046)
	.word gs(.L1028)
	.word gs(.L1047)
	.word gs(.L1048)
	.word gs(.L1049)
	.word gs(.L1050)
	.word gs(.L1051)
.LVL1452:
.L1037:
	.loc 11 299 0
	cpi r24,lo8(4)
	breq .+2
	rjmp .L1041
.LVL1453:
	movw r30,r6
	subi r30,-100
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
.LVL1454:
	movw r18,r24
	andi r18,6
	clr r19
	or r18,r19
	breq .+2
	rjmp .L1041
	sbiw r30,3
	ld r19,Z
	sbiw r30,1
	ld r18,Z
	cpse r19,r18
	rjmp .L1041
	.loc 11 300 0
	sbrs r24,7
	rjmp .L1041
	.loc 11 301 0
	movw r24,r6
	adiw r24,45
	call r32
.LVL1455:
	movw r2,r22
.LVL1456:
	movw r4,r24
	movw r24,r6
	adiw r24,41
	call r32
.LVL1457:
	.loc 11 300 0
	cp r2,r22
	cpc r3,r23
	cpc r4,r24
	cpc r5,r25
	breq .+2
	rjmp .L1041
	.loc 11 301 0
	movw r30,r6
	subi r30,-103
	sbci r31,-1
	ld r24,Z
	cpse r24,__zero_reg__
	rjmp .L1041
	.loc 11 302 0
	sbiw r30,5
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	sbiw r24,2
	sbiw r24,3
	brlo .+2
	rjmp .L1041
	.loc 11 303 0
	ldi r22,0
	movw r24,r6
	call guarded
.LVL1458:
	cpse r24,__zero_reg__
	rjmp .L1170
	.loc 11 304 0
	movw r24,r8
.LVL1459:
	adiw r24,52
	call r64
.LVL1460:
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r6
	subi r24,-128
	sbci r25,-1
	call lease_valid.isra.2
.LVL1461:
	tst r24
	brne .+2
	rjmp .L1165
.L1038:
	.loc 11 316 0
	movw r24,r14
	call r32
.LVL1462:
	movw r2,r22
	movw r4,r24
	ldd r24,Y+10
	ldd r25,Y+11
	call r32
.LVL1463:
	cp r2,r22
	cpc r3,r23
	cpc r4,r24
	cpc r5,r25
	brne .+2
	rjmp .L1043
.L1171:
.LBE936:
.LBE986:
	ldi r24,lo8(23)
	mov r13,r24
	rjmp .L1028
.LVL1464:
.L1039:
.LBB987:
.LBB937:
	.loc 11 308 0
	cpi r24,lo8(5)
	breq .+2
	rjmp .L1169
	movw r30,r6
	subi r30,-97
	sbci r31,-1
	ld r25,Z
	sbiw r30,1
	ld r24,Z
	cpse r25,r24
	rjmp .L1169
	.loc 11 309 0
	adiw r30,4
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	eor r25,r24
	andi r24,6
	clr r25
	.loc 11 308 0
	or r24,r25
	breq .+2
	rjmp .L1169
	.loc 11 310 0
	movw r24,r8
	adiw r24,60
	call r32
.LVL1465:
	movw r2,r22
.LVL1466:
	movw r4,r24
	movw r24,r6
	adiw r24,41
	call r32
.LVL1467:
	.loc 11 309 0
	cp r2,r22
	cpc r3,r23
	cpc r4,r24
	cpc r5,r25
	breq .+2
	rjmp .L1169
	.loc 11 311 0
	movw r22,r4
	movw r20,r2
	rjmp .L1261
.LVL1468:
.L1044:
	.loc 11 320 0
	ldi r24,lo8(2)
	movw r30,r6
	subi r30,-93
	sbci r31,-1
	st Z,r24
	ldi r22,lo8(8)
	ldi r23,0
	movw r24,r6
	call add_flags
.LVL1469:
	rjmp .L1028
.L1046:
	.loc 11 321 0
	movw r24,r8
	adiw r24,52
	call r64
.LVL1470:
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r6
	adiw r24,33
	call w64
.LVL1471:
	rjmp .L1028
.L1047:
	.loc 11 322 0
	movw r24,r8
	adiw r24,60
	call r32
.LVL1472:
	movw r20,r22
	movw r22,r24
	movw r24,r6
	call acknowledge.lto_priv.9
.LVL1473:
	rjmp .L1028
.L1048:
	.loc 11 323 0
	ldi r18,0
	ldi r20,lo8(4)
	ldi r22,lo8(2)
	ldi r23,0
	movw r24,r6
	call loss
.LVL1474:
	rjmp .L1028
.L1049:
.LBB922:
	.loc 11 325 0
	movw r10,r6
	ldi r18,100
	add r10,r18
	adc r11,__zero_reg__
	movw r26,r10
	ld r24,X+
	ld r25,X
	eor r25,r24
	eor r24,r25
	eor r25,r24
	movw r30,r24
	andi r30,9
	clr r31
	std Y+7,r31
	std Y+6,r30
.LVL1475:
	.loc 11 326 0
	movw r14,r6
	ldi r31,-124
	add r14,r31
	adc r15,__zero_reg__
	movw r26,r14
	ld r4,X+
	ld r5,X
	sbiw r26,1
	movw r30,r4
.LVL1476:
	subi r30,-116
	sbci r31,-1
	sbiw r26,6
	ld r24,X
	st Z,r24
	.loc 11 327 0
	movw r2,r6
	ldi r27,73
	add r2,r27
	adc r3,__zero_reg__
	movw r24,r2
	call r64
.LVL1477:
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r4
	subi r24,-96
	sbci r25,-1
	call w64
.LVL1478:
	.loc 11 328 0
	movw r30,r14
	ld r24,Z
	ldd r25,Z+1
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	subi r24,-104
	sbci r25,-1
	call w64
.LVL1479:
	.loc 11 332 0
	movw r30,r14
	ld r26,Z
	ldd r27,Z+1
	subi r26,112
	sbci r27,-1
	ldi r24,lo8(4)
	sbiw r30,10
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 333 0
	movw r30,r14
	ld r26,Z
	ldd r27,Z+1
	subi r26,108
	sbci r27,-1
	ldi r24,lo8(8)
	sbiw r30,18
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 334 0
	movw r30,r14
	ld r26,Z
	ldd r27,Z+1
	subi r26,100
	sbci r27,-1
	ldi r24,lo8(4)
	sbiw r30,22
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 335 0
	movw r26,r14
	ld r24,X+
	ld r25,X
	movw r30,r24
	subi r30,90
	sbci r31,-1
	st Z,__zero_reg__
	subi r24,114
	sbci r25,-1
	movw r30,r24
	st Z,__zero_reg__
.LVL1480:
.LBB923:
.LBB924:
	.loc 11 35 0
	movw r26,r10
	st X,__zero_reg__
.LBE924:
.LBE923:
	.loc 11 336 0
	ldd r24,Y+6
	ldd r25,Y+7
	ori r24,16
.LVL1481:
.LBB926:
.LBB925:
	.loc 11 35 0
	movw r30,r6
	subi r30,-101
	sbci r31,-1
	st Z,r24
.LVL1482:
.LBE925:
.LBE926:
	.loc 11 337 0
	movw r24,r8
	adiw r24,52
	call r64
.LVL1483:
	movw r16,r18
	movw r18,r20
	movw r20,r22
	movw r22,r24
	movw r24,r6
	adiw r24,33
	call w64
.LVL1484:
	movw r30,r6
	subi r30,-128
	sbci r31,-1
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	ldd r16,Z+12
	ldd r17,Z+13
	ldd r18,Z+14
	ldd r19,Z+15
	ldd r20,Z+16
	ldd r21,Z+17
	ldd r22,Z+18
	ldd r23,Z+19
	movw r24,r6
	adiw r24,49
	call w64
.LVL1485:
	.loc 11 338 0
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	movw r24,r6
	adiw r24,57
	call w64
.LVL1486:
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	movw r24,r6
	subi r24,-65
	sbci r25,-1
	call w64
.LVL1487:
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	movw r24,r2
	call w64
.LVL1488:
	.loc 11 339 0
	ldi r24,lo8(22)
	movw r30,r6
	subi r30,-106
	sbci r31,-1
	movw r26,r30
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
.LVL1489:
.LBB927:
.LBB928:
	.loc 11 35 0
	sbiw r30,8
	st Z,__zero_reg__
	adiw r30,1
	st Z,__zero_reg__
.LVL1490:
.LBE928:
.LBE927:
	.loc 11 340 0
	sbiw r30,5
	st Z,__zero_reg__
	adiw r30,1
	st Z,__zero_reg__
	adiw r30,10
	st Z,__zero_reg__
	sbiw r30,8
	st Z,__zero_reg__
	.loc 11 341 0
	ldi r24,lo8(1)
	sbiw r30,4
.LVL1491:
.L1246:
.LBE922:
	.loc 11 346 0
	st Z,r24
	rjmp .L1028
.LVL1492:
.L1050:
	.loc 11 344 0
	movw r30,r6
	subi r30,-93
	sbci r31,-1
	ld r24,Z
	cpi r24,lo8(4)
	brne .L1052
	ldi r24,lo8(5)
	st Z,r24
	adiw r30,1
	rjmp .L1246
.L1052:
	.loc 11 345 0
	subi r24,lo8(-(-5))
	cpi r24,lo8(2)
	brsh .+2
	rjmp .L1028
	.loc 11 346 0
	ldi r18,0
	ldi r20,lo8(5)
	ldi r22,lo8(1)
	ldi r23,0
	movw r24,r6
	call loss
.LVL1493:
	ldi r24,lo8(5)
	movw r30,r6
	subi r30,-94
	sbci r31,-1
	rjmp .L1246
.L1051:
.LBB929:
	.loc 11 350 0
	movw r24,r6
	call r32
.LVL1494:
	movw r2,r22
	movw r4,r24
.LVL1495:
	.loc 11 351 0
	movw r24,r8
	adiw r24,60
	call r32
.LVL1496:
	movw r20,r22
	movw r22,r24
	movw r24,r6
	call acknowledge.lto_priv.9
.LVL1497:
	ldi r24,lo8(-128)
	movw r30,r6
	0:
	st Z+,__zero_reg__
	dec r24
	brne 0b
	movw r22,r4
	movw r20,r2
	movw r24,r6
	call w32
.LVL1498:
	ldi r24,lo8(-1)
	movw r30,r6
	subi r30,-104
	sbci r31,-1
	st Z,r24
	.loc 11 352 0
	adiw r30,24
	ld r24,Z
	ldd r25,Z+1
	movw r26,r24
	subi r26,-110
	sbci r27,-1
	st X,__zero_reg__
	subi r24,-117
	sbci r25,-1
	ldi r18,lo8(-64)
	movw r26,r24
	0:
	st X+,__zero_reg__
	dec r18
	brne 0b
	.loc 11 353 0
	ld r26,Z
	ldd r27,Z+1
	movw r18,r26
	subi r18,-53
	sbci r19,-2
	ldi r24,lo8(69)
	movw r26,r18
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	movw r26,r30
	subi r26,-111
	sbci r27,-1
	st X,__zero_reg__
.LVL1499:
	.loc 11 354 0
	sbiw r26,37
	ld r14,X+
	ld r15,X
	ldi r27,95
	and r14,r27
	clr r15
.LBB930:
.LBB931:
	.loc 1 606 0
	ldd r16,Z+12
	ldd r17,Z+13
	ldd r18,Z+14
	ldd r19,Z+15
	ldd r20,Z+16
	ldd r21,Z+17
	ldd r22,Z+18
	ldd r23,Z+19
	movw r24,r30
	call update
.LVL1500:
	rjmp .L1028
.LVL1501:
.L1152:
.LBE931:
.LBE930:
.LBE929:
.LBE937:
.LBE987:
	.loc 11 274 0
	ldi r21,lo8(8)
	mov r13,r21
.LVL1502:
	rjmp .L1028
.LVL1503:
.L1153:
	.loc 11 278 0
	ldi r20,lo8(11)
	mov r13,r20
.LVL1504:
	rjmp .L1028
.LVL1505:
.L1155:
	.loc 11 313 0
	clr r13
	inc r13
.LVL1506:
	rjmp .L1028
.LVL1507:
.L1169:
	.loc 11 310 0
	ldi r25,lo8(7)
	mov r13,r25
.LVL1508:
	rjmp .L1028
.LVL1509:
.L1097:
	.loc 11 461 0
	ldi r31,lo8(1)
	std Y+1,r31
	rjmp .L1248
.LVL1510:
.L1099:
	.loc 11 437 0
	std Y+1,__zero_reg__
	mov r4,__zero_reg__
.LVL1511:
.L1257:
	.loc 11 426 0
	ldi r18,lo8(8)
	mov r13,r18
	rjmp .L1005
.LVL1512:
.L1100:
	.loc 11 437 0
	std Y+1,__zero_reg__
	mov r4,__zero_reg__
.LVL1513:
.L1254:
	.loc 11 200 0
	ldi r27,lo8(7)
	mov r13,r27
	rjmp .L1005
.L1101:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	rjmp .L1254
.L1102:
	std Y+1,__zero_reg__
	mov r4,r5
	rjmp .L1254
.L1104:
	ldd r5,Y+1
.LVL1514:
.L1262:
	mov r4,__zero_reg__
.L1249:
	.loc 11 221 0
	ldi r20,lo8(6)
	mov r13,r20
	rjmp .L1005
.LVL1515:
.L1107:
	.loc 11 437 0
	ldd r5,Y+1
.LVL1516:
.L1253:
.LBB988:
.LBB973:
	.loc 11 220 0
	mov r13,r4
	rjmp .L1256
.LVL1517:
.L1108:
.LBE973:
.LBE988:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	.loc 11 204 0
	ldi r26,lo8(10)
	mov r13,r26
	rjmp .L1005
.L1124:
	.loc 11 437 0
	mov r5,__zero_reg__
	mov r4,__zero_reg__
.LVL1518:
.L1252:
	.loc 11 206 0
	ldi r31,lo8(11)
	mov r13,r31
	rjmp .L1005
.LVL1519:
.L1127:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	rjmp .L1252
.L1129:
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	.loc 11 207 0
	clr r13
	inc r13
	rjmp .L1005
.L1132:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	.loc 11 210 0
	ldi r23,lo8(12)
	mov r13,r23
	rjmp .L1005
.LVL1520:
.L1135:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	.loc 11 214 0
	ldi r21,lo8(3)
	mov r13,r21
	rjmp .L1005
.LVL1521:
.L1138:
	.loc 11 437 0
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	rjmp .L1253
.L1139:
	mov r5,__zero_reg__
	rjmp .L1262
.LVL1522:
.L1141:
	mov r5,__zero_reg__
	std Y+1,__zero_reg__
	rjmp .L1249
.LVL1523:
.L1142:
	mov r5,__zero_reg__
	mov r4,r13
.LVL1524:
	.loc 11 222 0
	ldi r19,lo8(16)
	mov r13,r19
	rjmp .L1005
.LVL1525:
.L1143:
	.loc 11 465 0
	ldd r13,Y+1
.LVL1526:
.L1250:
	.loc 11 437 0
	std Y+1,__zero_reg__
	rjmp .L1005
.LVL1527:
.L1145:
	ldd r5,Y+1
.LVL1528:
	rjmp .L1257
.LVL1529:
.L1146:
	mov r5,__zero_reg__
.LVL1530:
	.loc 11 427 0
	ldi r25,lo8(20)
	mov r13,r25
	rjmp .L1005
.LVL1531:
.L1148:
	.loc 11 437 0
	mov r5,__zero_reg__
	rjmp .L1247
.LVL1532:
.L1054:
	.loc 11 474 0
	tst r13
	breq .L1055
	clr r4
	dec r4
.LVL1533:
.L1055:
.LBB989:
.LBB990:
	.loc 11 394 0
	ldi r24,lo8(66)
	ldd r26,Y+58
	ldd r27,Y+59
	0:
	st X+,__zero_reg__
	dec r24
	brne 0b
	ldi r24,lo8(2)
	ldd r30,Y+58
	ldd r31,Y+59
	st Z,r24
	movw r26,r8
	adiw r26,1
	ld r24,X
	ori r24,lo8(-128)
	std Z+1,r24
	.loc 11 395 0
	ldd r20,Y+20
	ldd r21,Y+21
	ldd r22,Y+22
	ldd r23,Y+23
	movw r24,r30
	adiw r24,2
	call w32
.LVL1534:
	ldd r30,Y+58
	ldd r31,Y+59
	std Z+6,r13
	std Z+7,r4
.LVL1535:
	.loc 11 396 0
	movw r26,r6
	adiw r26,4
	ld r24,X
	cpi r24,lo8(2)
	breq .+2
	rjmp .L1056
	.loc 11 397 0
	movw r30,r6
	subi r30,-128
	sbci r31,-1
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	subi r30,-119
	sbci r31,-1
	ldi r24,lo8(42)
	ldd r26,Y+58
	ldd r27,Y+59
	adiw r26,8
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 398 0
	ldi r24,lo8(8)
	movw r30,r6
	adiw r30,5
	ldd r26,Y+58
	ldd r27,Y+59
	adiw r26,50
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(8)
	movw r30,r6
	adiw r30,41
	ldd r26,Y+58
	ldd r27,Y+59
	adiw r26,58
.L1258:
	.loc 11 399 0
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
.L1057:
.LVL1536:
.LBE990:
.LBE989:
	.loc 11 476 0
	ldd r30,Y+60
	ldd r31,Y+61
	sbiw r30,0
	brne .+2
	rjmp .L1259
	.loc 11 477 0
	ldi r24,lo8(66)
	ldi r25,0
	std Z+1,r25
	st Z,r24
	.loc 11 478 0
	cpse r13,__zero_reg__
	rjmp .L1259
	ldi r31,lo8(-1)
	cp r4,r31
	brne .+2
	rjmp .L1259
	ldd r26,Y+58
	ldd r27,Y+59
	subi r26,-66
	sbci r27,-1
	.loc 11 479 0
	ldd r18,Y+1
.LBB992:
.LBB993:
	.loc 11 407 0
	movw r30,r6
.LBE993:
.LBE992:
	.loc 11 479 0
	tst r18
	brne .+2
	rjmp .L1059
.LVL1537:
.LBB1004:
.LBB1002:
	.loc 11 407 0
	subi r30,-128
	sbci r31,-1
	ld r14,Z
	ldd r15,Z+1
.LVL1538:
	ldd r20,Y+58
	ldd r21,Y+59
	subi r20,-114
	sbci r21,-1
	movw r12,r20
	.loc 11 408 0
	cpse r4,__zero_reg__
	rjmp .L1060
	.loc 11 409 0
	ldi r18,lo8(16)
	movw r20,r26
	ldi r22,0
	movw r24,r14
	call constants
.LVL1539:
	ldd r20,Y+58
	ldd r21,Y+59
	subi r20,-82
	sbci r21,-1
	ldi r18,lo8(32)
	ldi r22,lo8(1)
	movw r24,r14
	call constants
.LVL1540:
	.loc 11 410 0
	ldi r18,lo8(32)
	movw r20,r12
	ldi r22,lo8(2)
	movw r24,r14
	call constants
.LVL1541:
.LBE1002:
.LBE1004:
	ldi r24,lo8(80)
	ldi r25,0
.LVL1542:
.L1061:
	.loc 11 479 0
	subi r24,-66
	sbci r25,-1
	ldd r30,Y+60
	ldd r31,Y+61
	std Z+1,r25
	st Z,r24
	.loc 11 491 0
	ldd r4,Y+1
.LVL1543:
	jmp .L983
.LVL1544:
.L1056:
.LBB1005:
.LBB991:
	.loc 11 399 0
	ldd r30,Y+46
	ldd r31,Y+47
	sbiw r30,44
	brsh .+2
	rjmp .L1057
	movw r26,r8
	adiw r26,1
	ld r24,X
	cpi r24,lo8(64)
	brsh .+2
	rjmp .L1057
	movw r30,r8
	adiw r30,2
	ldi r24,lo8(42)
	ldd r26,Y+58
	ldd r27,Y+59
	adiw r26,8
	rjmp .L1258
.LVL1545:
.L1060:
.LBE991:
.LBE1005:
.LBB1006:
.LBB1003:
	.loc 11 412 0
	movw r30,r14
	ldd r20,Z+28
	ldd r21,Z+29
	ldd r22,Z+30
	ldd r23,Z+31
	movw r24,r26
	call w32
.LVL1546:
	movw r30,r14
	subi r30,-72
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
.LVL1547:
.LBB994:
.LBB995:
	.loc 11 35 0
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-70
	sbci r31,-1
	st Z,r25
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-71
	sbci r31,-1
	st Z,r24
.LVL1548:
.LBE995:
.LBE994:
	.loc 11 413 0
	ldd r26,Y+58
	ldd r27,Y+59
	subi r26,-72
	sbci r27,-1
	movw r30,r14
	subi r30,-76
	sbci r31,-1
	ldi r24,lo8(32)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	movw r26,r14
	adiw r26,12
	ld r16,X
	sbiw r26,12
	adiw r26,13
	ld r17,X
	sbiw r26,13
	adiw r26,14
	ld r18,X
	sbiw r26,14
	adiw r26,15
	ld r19,X
	sbiw r26,15
	adiw r26,16
	ld r20,X
	sbiw r26,16
	adiw r26,17
	ld r21,X
	sbiw r26,17
	adiw r26,18
	ld r22,X
	sbiw r26,18
	adiw r26,19
	ld r23,X
	ldd r24,Y+58
	ldd r25,Y+59
	subi r24,-104
	sbci r25,-1
	call w64
.LVL1549:
	.loc 11 414 0
	movw r30,r14
	subi r30,-74
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
.LVL1550:
.LBB996:
.LBB997:
	.loc 11 35 0
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-112
	sbci r31,-1
	st Z,r25
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-113
	sbci r31,-1
	st Z,r24
.LVL1551:
.LBE997:
.LBE996:
	.loc 11 414 0
	movw r30,r14
	subi r30,-108
	sbci r31,-1
	ld r24,Z
	movw r30,r12
	st Z,r24
	movw r26,r14
	ld r30,X+
	ld r31,X
	ldd r24,Z+16
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-115
	sbci r31,-1
	st Z,r24
	.loc 11 415 0
	movw r30,r6
	ldd r24,Z+4
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-116
	sbci r31,-1
	st Z,r24
	movw r16,r6
	subi r16,126
	sbci r17,-1
	movw r26,r16
	ld r30,X+
	ld r31,X
	ldd r24,Z+14
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-117
	sbci r31,-1
	st Z,r24
.LVL1552:
.LBB998:
.LBB999:
	.loc 11 35 0
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-118
	sbci r31,-1
	st Z,__zero_reg__
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-119
	sbci r31,-1
	ldi r24,lo8(1)
	st Z,r24
.LVL1553:
.LBE999:
.LBE998:
	.loc 11 416 0
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-120
	sbci r31,-1
	ldi r25,lo8(2)
	st Z,r25
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-121
	sbci r31,-1
	st Z,r25
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-122
	sbci r31,-1
	ldi r25,lo8(32)
	st Z,r25
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,-123
	sbci r31,-1
	st Z,r24
	.loc 11 417 0
	movw r26,r14
	ld r30,X+
	ld r31,X
	ldd r20,Z+12
	ldd r21,Z+13
	ldd r22,Z+14
	ldd r23,Z+15
	ldd r24,Y+58
	ldd r25,Y+59
	subi r24,-124
	sbci r25,-1
	call w32
.LVL1554:
	movw r26,r16
	ld r30,X+
	ld r31,X
	ldd r20,Z+8
	ldd r21,Z+9
	ldd r22,Z+10
	ldd r23,Z+11
	ldd r24,Y+58
	ldd r25,Y+59
	subi r24,-128
	sbci r25,-1
	call w32
.LVL1555:
	.loc 11 418 0
	movw r26,r16
	ld r30,X+
	ld r31,X
	ldd r24,Z+12
	ldd r25,Z+13
.LVL1556:
.LBB1000:
.LBB1001:
	.loc 11 35 0
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,124
	sbci r31,-1
	st Z,r25
	ldd r30,Y+58
	ldd r31,Y+59
	subi r30,123
	sbci r31,-1
	st Z,r24
.LVL1557:
.LBE1001:
.LBE1000:
	.loc 11 419 0
	ldi r22,0
	movw r24,r6
	call source_epoch
.LVL1558:
	movw r20,r22
	movw r22,r24
	ldd r24,Y+58
	ldd r25,Y+59
	subi r24,122
	sbci r25,-1
	call w32
.LVL1559:
	ldi r22,lo8(1)
	movw r24,r6
	call source_epoch
.LVL1560:
	movw r20,r22
	movw r22,r24
	ldd r24,Y+58
	ldd r25,Y+59
	subi r24,118
	sbci r25,-1
	call w32
.LVL1561:
	.loc 11 420 0
	movw r24,r6
	call r32
.LVL1562:
	movw r20,r22
	movw r22,r24
	ldd r24,Y+58
	ldd r25,Y+59
	subi r24,114
	sbci r25,-1
	call w32
.LVL1563:
	movw r30,r14
	ldd r20,Z+32
	ldd r21,Z+33
	ldd r22,Z+34
	ldd r23,Z+35
	ldd r24,Y+58
	ldd r25,Y+59
	subi r24,110
	sbci r25,-1
	call w32
.LVL1564:
	ldi r31,40
	add r14,r31
	adc r15,__zero_reg__
.LVL1565:
	ldd r16,Y+58
	ldd r17,Y+59
	subi r16,106
	sbci r17,-1
	ldd r12,Y+58
	ldd r13,Y+59
	ldi r18,-74
	add r12,r18
	adc r13,__zero_reg__
.LVL1566:
.L1062:
	.loc 11 421 0
	movw r26,r14
	ld r20,X+
	ld r21,X+
	ld r22,X+
	ld r23,X+
	movw r14,r26
	movw r24,r16
	call w32
.LVL1567:
	subi r16,-4
	sbci r17,-1
	cp r12,r16
	cpc r13,r17
	brne .L1062
.LBE1003:
.LBE1006:
	.loc 11 422 0
	ldi r24,lo8(116)
	ldi r25,0
	rjmp .L1061
.LVL1568:
.L1059:
	.loc 11 480 0
	cpse r4,__zero_reg__
	rjmp .L1063
	.loc 11 481 0
	adiw r30,4
	ldi r24,lo8(124)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	.loc 11 484 0
	movw r30,r6
	subi r30,-100
	sbci r31,-1
	ld r24,Z
	ldd r25,Z+1
	eor r25,r24
	eor r24,r25
	sbrc r24,7
	rjmp .L1064
	ldi r16,lo8(-1)
	ldi r17,lo8(-1)
	ldi r18,lo8(-1)
	ldi r19,lo8(-1)
	ldi r20,lo8(-1)
	ldi r21,lo8(-1)
	ldi r22,lo8(-1)
	ldi r23,lo8(-1)
	ldd r24,Y+58
	ldd r25,Y+59
	subi r24,121
	sbci r25,-1
	call w64
.LVL1569:
.L1064:
	.loc 11 485 0
	ldi r24,lo8(-66)
	ldi r25,0
	ldd r26,Y+60
	ldd r27,Y+61
	st X+,r24
	st X,r25
	jmp .L1259
.L1063:
	subi r30,124
	sbci r31,-1
	ld __tmp_reg__,Z+
	ld r31,Z
	mov r30,__tmp_reg__
	.loc 11 487 0
	ldi r18,lo8(1)
	cpse r4,r18
	rjmp .L1065
	subi r30,-120
	sbci r31,-1
	ldi r24,lo8(48)
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(114)
	ldi r25,0
	ldd r26,Y+60
	ldd r27,Y+61
	st X+,r24
	st X,r25
	jmp .L983
.L1065:
	.loc 11 488 0
	ldi r24,lo8(44)
	mul r5,r24
	add r30,r0
	adc r31,r1
	clr __zero_reg__
	subi r30,88
	sbci r31,-1
	0:
	ld r0,Z+
	st X+,r0
	dec r24
	brne 0b
	ldi r24,lo8(110)
	ldi r25,0
	ldd r30,Y+60
	ldd r31,Y+61
	std Z+1,r25
	st Z,r24
	jmp .L1259
.LVL1570:
.L991:
.LBB1007:
.LBB912:
	.loc 11 373 0
	ldd r20,Y+46
	ldd r21,Y+47
	cpi r20,3
	cpc r21,__zero_reg__
	breq .+4
	jmp .L1175
	.loc 11 374 0
	movw r26,r8
	adiw r26,2
	ld r24,X
	cpi r24,lo8(2)
	brsh .+4
	jmp .L995
.LVL1571:
.L1081:
.LBE912:
.LBE1007:
	ldi r20,lo8(25)
	mov r5,r20
.LVL1572:
	jmp .L990
.LVL1573:
.L1000:
.LBB1008:
.LBB913:
	.loc 11 387 0
	cpi r17,lo8(71)
	breq .+4
	jmp .L999
	.loc 11 388 0
	sbiw r24,1
	brne .+4
	jmp .L995
	jmp .L1090
.LVL1574:
.L1003:
.LBE913:
.LBE1008:
	.loc 11 455 0
	tst r5
	brne .+4
	jmp .L1006
.L1255:
	.loc 11 437 0
	mov r4,__zero_reg__
	.loc 11 455 0
	mov r13,r5
	rjmp .L1251
	.cfi_endproc
.LFE160:
	.size	hms_standing_handle, .-hms_standing_handle
