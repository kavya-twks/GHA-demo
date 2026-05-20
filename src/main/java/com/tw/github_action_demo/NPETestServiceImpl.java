package com.tw.github_action_demo;

import java.util.Optional;

public class NPETestServiceImpl {

    public void testNPE() {
        final Integer p = null;
        Optional.ofNullable(p)
                .ifPresent(value -> System.out.println(value.compareTo(10)));
    }
}