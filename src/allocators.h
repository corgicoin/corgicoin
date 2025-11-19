// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2012 The Bitcoin developers
// Copyright (c) 2011-2012 Litecoin Developers
// Copyright (c) 2013 Dogecoin Developers
// Copyright (c) 2014 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_ALLOCATORS_H
#define BITCOIN_ALLOCATORS_H

#include <string.h>
#include <string>

#ifdef WIN32
#ifdef _WIN32_WINNT
#undef _WIN32_WINNT
#endif
#define _WIN32_WINNT 0x0501
#define WIN32_LEAN_AND_MEAN 1
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
// This is used to attempt to keep keying material out of swap
// Note that VirtualLock does not provide this as a guarantee on Windows,
// but, in practice, memory that has been VirtualLock'd almost never gets written to
// the pagefile except in rare circumstances where memory is extremely low.
#define mlock(p, n) VirtualLock((p), (n));
#define munlock(p, n) VirtualUnlock((p), (n));
#else
#include <sys/mman.h>
#include <limits.h>
/* This comes from limits.h if it's not defined there set a sane default */
#ifndef PAGESIZE
#include <unistd.h>
#define PAGESIZE sysconf(_SC_PAGESIZE)
#endif
#define mlock(a,b) \
  mlock(((void *)(((size_t)(a)) & (~((PAGESIZE)-1)))),\
  (((((size_t)(a)) + (b) - 1) | ((PAGESIZE) - 1)) + 1) - (((size_t)(a)) & (~((PAGESIZE) - 1))))
#define munlock(a,b) \
  munlock(((void *)(((size_t)(a)) & (~((PAGESIZE)-1)))),\
  (((((size_t)(a)) + (b) - 1) | ((PAGESIZE) - 1)) + 1) - (((size_t)(a)) & (~((PAGESIZE) - 1))))
#endif

//
// Allocator that locks its contents from being paged
// out of memory and clears its contents before deletion.
//
template<typename T>
struct secure_allocator : public std::allocator<T>
{
    // MSVC8 default copy constructor is broken
    using base = std::allocator<T>;
    using size_type = typename base::size_type;
    using difference_type = typename base::difference_type;
    using pointer = typename base::pointer;
    using const_pointer = typename base::const_pointer;
    using reference = typename base::reference;
    using const_reference = typename base::const_reference;
    using value_type = typename base::value_type;
    secure_allocator() noexcept = default;
    secure_allocator(const secure_allocator& a) throw() : base(a) {}
    template <typename U>
    secure_allocator(const secure_allocator<U>& a) throw() : base(a) {}
    ~secure_allocator() noexcept = default;
    template<typename _Other> struct rebind
    { using other = secure_allocator<_Other>; };

    T* allocate(std::size_t n, const void *hint = 0)
    {
        T *p;
        p = std::allocator<T>::allocate(n, hint);
        if (p != nullptr)
            mlock(p, sizeof(T) * n);
        return p;
    }

    void deallocate(T* p, std::size_t n)
    {
        if (p != nullptr)
        {
            memset(p, 0, sizeof(T) * n);
            munlock(p, sizeof(T) * n);
        }
        std::allocator<T>::deallocate(p, n);
    }
};


//
// Allocator that clears its contents before deletion.
//
template<typename T>
struct zero_after_free_allocator : public std::allocator<T>
{
    // MSVC8 default copy constructor is broken
    using base = std::allocator<T>;
    using size_type = typename base::size_type;
    using difference_type = typename base::difference_type;
    using pointer = typename base::pointer;
    using const_pointer = typename base::const_pointer;
    using reference = typename base::reference;
    using const_reference = typename base::const_reference;
    using value_type = typename base::value_type;
    zero_after_free_allocator() noexcept = default;
    zero_after_free_allocator(const zero_after_free_allocator& a) throw() : base(a) {}
    template <typename U>
    zero_after_free_allocator(const zero_after_free_allocator<U>& a) throw() : base(a) {}
    ~zero_after_free_allocator() noexcept = default;
    template<typename _Other> struct rebind
    { using other = zero_after_free_allocator<_Other>; };

    void deallocate(T* p, std::size_t n)
    {
        if (p != nullptr)
            memset(p, 0, sizeof(T) * n);
        std::allocator<T>::deallocate(p, n);
    }
};

// This is exactly like std::string, but with a custom allocator.
// Modern C++11 type alias for secure string
using SecureString = std::basic_string<char, std::char_traits<char>, secure_allocator<char>>;

#endif
