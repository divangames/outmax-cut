"""Cheap frame checks during assembly; findings request review, never discard footage."""
import cv2
import numpy as np


class FrameQuality:
    def __init__(self):
        self.black=[];self.freezes=[];self.previous=None;self.first=None;self.last=None;self.still_start=None;self.count=0

    def add(self, frame, index, eligible=True):
        small=cv2.cvtColor(cv2.resize(frame,(64,64)),cv2.COLOR_BGR2GRAY)
        if self.first is None:self.first=small.copy()
        if np.mean(small<8)>.995:self.black.append(index)
        stationary=eligible and self.previous is not None and float(np.mean(cv2.absdiff(small,self.previous)))<.12 and float(np.std(small))>7
        if stationary and self.still_start is None:self.still_start=index-1
        if not stationary and self.still_start is not None:
            if index-self.still_start>=90:self.freezes.append([self.still_start/30,index/30])
            self.still_start=None
        self.previous=small;self.last=small;self.count=index+1

    def report(self):
        spans=list(self.freezes)
        if self.still_start is not None and self.count-self.still_start>=90:spans.append([self.still_start/30,self.count/30])
        difference=float(np.mean(cv2.absdiff(self.first,self.last))) if self.first is not None else 0
        findings=[]
        if self.black:findings.append(dict(kind='black',time=self.black[0]/30,count=len(self.black),message='Есть почти чёрные кадры'))
        for start,end in spans[:10]:findings.append(dict(kind='freeze',time=start,end=end,message='Подозрительно неподвижный участок: проверьте демонстрацию'))
        if difference>15:findings.append(dict(kind='loop',time=0,message='Заметно различаются первый и последний кадры'))
        return dict(findings=findings,black_frames=len(self.black),loop_difference=round(difference,3),checked_frames=self.count)
