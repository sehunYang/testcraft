# -*- coding: utf-8 -*-
"""HWP 수식 폭·높이 모델 — 예시.hml 실측 25개로 교정"""
import re

def grab(s,i):
    d=0
    for j in range(i,len(s)):
        if s[j]=='{': d+=1
        elif s[j]=='}':
            d-=1
            if d==0: return s[i+1:j], j+1
    return s[i+1:], len(s)

SYM = {
    '<->':'↔','->':'→','<-':'←','pi':'π','theta':'θ','sim':'∼','times':'×','cdot':'·',
    'circ':'°','lambda':'λ','alpha':'α','beta':'β','gamma':'γ','delta':'δ','epsilon':'ε',
    'zeta':'ζ','eta':'η','iota':'ι','kappa':'κ','mu':'μ','nu':'ν','xi':'ξ','rho':'ρ',
    'sigma':'σ','tau':'τ','upsilon':'υ','phi':'φ','chi':'χ','psi':'ψ','omega':'ω',
    'varepsilon':'ϵ','vartheta':'ϑ','varpi':'ϖ','varsigma':'ς','varphi':'ϕ',
    'GAMMA':'Γ','DELTA':'Δ','THETA':'Θ','LAMBDA':'Λ','XI':'Ξ','PI':'Π','SIGMA':'Σ',
    'UPSILON':'Υ','PHI':'Φ','PSI':'Ψ','OMEGA':'Ω',
    'cos':'㏄','sin':'㏛','tan':'㏇','LEQ':'≤','GEQ':'≥','neq':'≠','APPROX':'≈',
    'PLUSMINUS':'±','MINUSPLUS':'∓','EQUIV':'≡','SIMEQ':'≃','SIM':'∼','PROPTO':'∝',
    'UNION':'∪','INTER':'∩','PARTIAL':'∂','NABLA':'∇','LDOTS':'…','cdots':'⋯',
    'VDOTS':'⋮','DDOTS':'⋱','IMAG':'ℑ','VERT':'∥','vert':'|','EMPTYSET':'∅',
    'TRIANGLE':'△','THEREFORE':'∴','BECAUSE':'∵',
}
W_LOWER, W_UPPER, W_DIGIT, W_OP, W_PAREN, W_SPACE, W_SYM, W_RAD = 660,800,550,1100,385,60,700,760
PAD = 150
SUB = 0.72

def _pre(s):
    for k,v in SYM.items():
        s = s.replace(k,v) if not k[0].isalpha() else re.sub(r'(?<![A-Za-z])%s(?![A-Za-z])'%k, v, s)
    return s

def _top_level_over(s):
    """Return the first native OVER delimiter outside all grouped terms."""
    depth = 0
    i = 0
    while i < len(s):
        if s[i] == '{':
            depth += 1
            i += 1
            continue
        if s[i] == '}':
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0 and s.startswith(' over ', i):
            return i
        i += 1
    return None

def _leading_group(s):
    """Return (contents, remaining text) for one leading balanced HWP group."""
    i = 0
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s) or s[i] != '{':
        j = i
        while j < len(s) and not s[j].isspace():
            j += 1
        return s[i:j], s[j:]
    depth = 0
    for j in range(i, len(s)):
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
            if depth == 0:
                return s[i + 1:j], s[j + 1:]
    return s[i + 1:], ''

def _fraction_width(s, sc=1.0):
    split = _top_level_over(s)
    if split is None:
        return None
    numerator = s[:split]
    denominator, tail = _leading_group(s[split + len(' over '):])
    return max(_w(numerator, sc), _w(denominator, sc)) + _w(tail, sc) + PAD * 2

def _contains_fraction(s):
    if _top_level_over(s) is not None:
        return True
    i = 0
    while i < len(s):
        if s[i] == '{':
            inner, i = grab(s, i)
            if _contains_fraction(inner):
                return True
            continue
        i += 1
    return False

def _w(s, sc=1.0):
    fraction = _fraction_width(s, sc)
    if fraction is not None:
        return fraction
    t=0.0; i=0
    while i < len(s):
        c=s[i]
        if s.startswith('root',i) and (i+4==len(s) or not s[i+4].isalnum()):
            i += 4
            while i<len(s) and s[i]==' ': i+=1
            if i<len(s) and s[i]=='{':
                index,i=grab(s,i)
                while i<len(s) and s[i]==' ': i+=1
                if s.startswith('of',i):
                    i += 2
                    while i<len(s) and s[i]==' ': i+=1
                    if i<len(s) and s[i]=='{':
                        radicand,i=grab(s,i)
                        t += W_RAD*sc + _w(index,sc*SUB) + _w(radicand,sc)
                        continue
                # A malformed native root should not cause the remaining
                # expression to disappear from the width estimate.
                t += W_RAD*sc + _w(index,sc)
            else:
                t += W_RAD*sc
            continue
        if s.startswith('sqrt',i):
            i+=4
            while i<len(s) and s[i]==' ': i+=1
            if i<len(s) and s[i]=='{':
                a,i=grab(s,i); t += W_RAD*sc + _w(a,sc)
            else:
                t += W_RAD*sc + _w(s[i],sc); i+=1
            continue
        if s.startswith('rm',i) and (i+2>=len(s) or not (s[i+2].isalnum())): i+=2; continue
        if s.startswith('vec',i): i+=3; continue
        if c in '_^':
            i+=1
            while i<len(s) and s[i]==' ': i+=1
            if i<len(s) and s[i]=='{': a,i=grab(s,i); t += _w(a, sc*SUB)
            elif i<len(s): t += _w(s[i], sc*SUB); i+=1
            continue
        if c=='{': a,i=grab(s,i); t += _w(a,sc); continue
        if c=='}': i+=1; continue
        if c.isdigit(): t += W_DIGIT*sc
        elif 'a'<=c<='z': t += W_LOWER*sc
        elif 'A'<=c<='Z': t += W_UPPER*sc
        elif c in '+-=<>:∼×·': t += W_OP*sc
        elif c in '(),.': t += W_PAREN*sc
        elif c==' ': t += W_SPACE*sc
        elif c=='°': t += 420*sc
        else: t += W_SYM*sc
        i+=1
    return t

def metrics(script):
    s=_pre(script)
    top_fraction = _fraction_width(s)
    if top_fraction is not None:
        w = top_fraction
    else:
        w = _w(s) + PAD
    if _contains_fraction(s):
        deep = 'sqrt' in s or 'root {' in s
        h, b = (3050, 50) if deep else (2800, 53)
    else:
        has_sub='_' in s; has_sup='^' in s
        if 'vec' in script:              h,b = 1575,75
        elif 'sqrt' in s or 'root {' in s: h,b = 1350,80
        elif has_sub and has_sup:        h,b = 1550,76
        elif has_sub:                    h,b = 1350,71
        elif has_sup:                    h,b = 1350,85
        else:                            h,b = 1125,85
    return int(min(24000, max(700, w*1.05))), h, b     # 5% 여유
