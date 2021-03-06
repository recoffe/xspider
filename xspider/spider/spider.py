#coding=utf-8



from b2 import log2
from b2 import rand2
from b2 import str2
from b2 import sort2 
from ..fetch.fetcher import BaseRequestsFetcher
from ..model.models import ZRequest
from ..model.page import Page
from ..pipeline.ConsolePipeLine import ConsolePipeLine
from ..queue.SpiderQueue import MemoryFifoQueue
from ..libs import links
from ..model.page import Page
from ..filters.UrlFilter import SiteFilter
from ..selector.CssSelector import CssSelector
from spiderlistener import DefaultSpiderListener
from spiderlistener import SpiderListener
import json

class BaseSpider(object):


    def __init__(self , name, *argv , **kw):
        self.log_level = kw.get("log_level" , "warn")
        self.logger = log2.get_stream_logger(self.log_level,name)
        self.name = name
        self.allow_site = kw.get("allow_site" , [])
        self.logger.info("spider {} init , allow_site {}".format(name,self.allow_site))
        self.start_urls = kw.get("start_urls" , [])
        self.page_processor = kw.get("page_processor")
        if self.page_processor is None:
            raise ValueError("page processor not set ! can't run ")
        self.fetcher = kw.get("fetcher" , BaseRequestsFetcher())
        self.pipelines = kw.get("pipeline" , [ConsolePipeLine()])
        self.run_flag = True
        self.spid = rand2.get_random_seq(10)
        self.url_pool = kw.get("queue" , MemoryFifoQueue(10000))
        self.logger.info("init")
        self.before_crawl = kw.get("before_crawl",[]) # before crawl do something
        self.site_filters = [SiteFilter(site) for site in self.allow_site]
        url_filters = kw.get("url_filters",[])
        sort2.sort_list_object(url_filters,"_priority")
        self.url_filters = url_filters 
        self.listeners = SpiderListener()
        self.listeners.addListener(kw.get("listeners" , [DefaultSpiderListener()]))
        self.link_extractors = CssSelector("a[href]")
        self.crawled_filter = kw.get("crawled_filter", None)

    def setStartUrls(self , urls):
        self.start_urls.extend(urls)

    def start(self, *argv , **kw):
        self.crawl_start()
        self._make_start_request(*argv , **kw)
        self.logger.info("spider {} get start request".format(self.name))
        while self.url_pool.empty() is False and self.run_flag:
            request = self.url_pool.pop()
            self.logger.info("get {req} ".format(req = request))
            links = set()
            for response in self.fetcher.fetch(request):
                page = Page(request , response , request["dir_path"])
                _links = self.extract_links(page)
                links.update(self.url_filter(_links))
                self.logger.debug("extract link {}".format(links))
                items = self.page_processor.excute(page,self)
                self.logger.debug("process items {} items {}".format(request["url"],json.dumps(items)))
                if items:
                    self.pipeline(items)
            for link in links:
                self.url_pool.push(ZRequest(link , request["dir_path"] , *argv , **kw))
        self.crawl_stop()


    def _make_start_request(self , *argv , **kw):
        for url in self.start_urls:
            self.logger.debug("add start url [{url}]".format(url = url))
            self.url_pool.push(ZRequest(url , 0 ,*argv , **kw ))

    def extract_links(self , page):
        parrent_link = page.request["url"]
        parrent_site = links.get_url_site(parrent_link)
        parrent_protocol = links.get_url_protocol(parrent_link)
        self.logger.debug("parrent_link {} parrent_site {} parrent_protocol {} ".format(parrent_link,parrent_site,parrent_protocol))
        return [ links.join_url(parrent_protocol,parrent_site , url["href"] ) for url in self.link_extractors.select(page) if not str2.isBlank(url["href"])  ]

    def pipeline(self , page ):
        for pipeline in self.pipelines:
            pipeline.process(page)

    def _filter(self,url_filters,url):
        """filter 
        """
        for url_filter in url_filters:
            _filter = url_filter.filter(url)
            # if url_filter must be check and url not match filter , so url filtered
            if _filter is True and url_filter.must_check():
                return False
            if not _filter:
                return True
        return False

    def url_filter(self , urls):
        if urls is None or len(urls) == 0:
            return []
        if len(self.site_filters):
            urls[:] = [ url for url in urls if self._filter(self.site_filters,url)]
        if len(self.url_filters):
            urls[:] = [ url for url in urls if self._filter(self.url_filters,url)]
        if self.crawled_filter:
            urls[:] = [url for url in urls if not self.crawled_filter.filter(url)]
        return urls

    def crawl_stop(self):
        self.listeners.notify("spider_stop" ,self)

    def crawl_start(self):
        self.listeners.notify("spider_start" ,self)
